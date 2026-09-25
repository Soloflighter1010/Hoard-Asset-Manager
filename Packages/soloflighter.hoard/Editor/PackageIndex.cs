// Which assets of each .unitypackage this project already has. Packages are read on a background thread (their
// GUIDs only; nothing is extracted), one at a time, and remembered in the project's Library folder so each is read
// once. Whether the project has a GUID is asked on the main thread, as Unity requires.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEditor;

namespace SoloFlighter.Hoard.Editor
{
    public enum InProject { Unknown, No, Partly, Yes }

    public sealed class PackageIndex
    {
        static readonly string CacheFile = Path.Combine("Library", "Hoard", "package-guids.json");
        readonly ConcurrentDictionary<string, string[]> guids = new ConcurrentDictionary<string, string[]>();   // "path|size|time" -> GUIDs
        readonly Dictionary<string, InProject> status = new Dictionary<string, InProject>();
        readonly ConcurrentQueue<string> waiting = new ConcurrentQueue<string>();
        readonly ConcurrentQueue<string> fresh = new ConcurrentQueue<string>();   // read since the last look
        readonly CancellationTokenSource stop = new CancellationTokenSource();
        int queued, done;
        volatile bool changed, cacheDirty;

        public int Waiting { get { return queued - done; } }

        public PackageIndex() { LoadCache(); }

        static string Stamp(string path)
        {
            var info = new FileInfo(path);
            return path + "|" + info.Length + "|" + info.LastWriteTimeUtc.Ticks;
        }

        /// <summary>Queue packages to be read in the background (ones already known are skipped).</summary>
        public void Want(IEnumerable<string> paths)
        {
            foreach (string p in paths)
            {
                if (p == null || !File.Exists(p) || guids.ContainsKey(Stamp(p))) continue;
                waiting.Enqueue(p);
                Interlocked.Increment(ref queued);
            }
            Task.Run(Work);
        }

        int working;
        void Work()
        {
            if (Interlocked.Exchange(ref working, 1) == 1) return;   // one reader at a time: kind to the disk
            try
            {
                string path;
                while (!stop.IsCancellationRequested && waiting.TryDequeue(out path))
                {
                    try
                    {
                        string stamp = Stamp(path);
                        if (!guids.ContainsKey(stamp))
                        {
                            var found = UnityPackageReader.ReadAssets(path);
                            guids[stamp] = new List<string>(found.Keys).ToArray();
                            cacheDirty = true;
                        }
                    }
                    catch (Exception) { guids[SafeStamp(path)] = new string[0]; }   // unreadable: counts as not a package
                    fresh.Enqueue(path);
                    Interlocked.Increment(ref done);
                    changed = true;
                }
            }
            finally { Interlocked.Exchange(ref working, 0); }
        }

        static string SafeStamp(string path) { try { return Stamp(path); } catch (Exception) { return path; } }

        /// <summary>Call from the editor's update loop: true when there's something new to show. The packages read
        /// since the last call are added to fresh (when given), so only their products need looking at again.</summary>
        public bool TakeChanges(List<string> freshPaths = null)
        {
            if (cacheDirty && Waiting == 0) SaveCache();
            if (!changed) return false;
            changed = false;
            string path;
            while (fresh.TryDequeue(out path))
            {
                status.Remove(path);   // only what's new is looked at again
                if (freshPaths != null) freshPaths.Add(path);
            }
            return true;
        }

        /// <summary>After the project changes (an import, a deletion), look again.</summary>
        public void ProjectChanged() { status.Clear(); }

        /// <summary>How much of the package the project has. Main thread only.</summary>
        public InProject Status(string path, out int have, out int total)
        {
            have = total = 0;
            string[] list;
            if (path == null || !File.Exists(path) || !guids.TryGetValue(Stamp(path), out list)) return InProject.Unknown;
            total = list.Length;
            foreach (string g in list) if (!string.IsNullOrEmpty(AssetDatabase.GUIDToAssetPath(g))) have++;
            if (total == 0) return InProject.Unknown;
            return have == 0 ? InProject.No : have == total ? InProject.Yes : InProject.Partly;
        }

        public InProject Status(string path)
        {
            InProject s;
            if (path != null && status.TryGetValue(path, out s)) return s;
            int have, total;
            s = Status(path, out have, out total);
            if (path != null) status[path] = s;
            return s;
        }

        public string[] Guids(string path)
        {
            string[] list;
            return path != null && File.Exists(path) && guids.TryGetValue(Stamp(path), out list) ? list : new string[0];
        }

        public void Stop() { stop.Cancel(); if (cacheDirty) SaveCache(); }

        void LoadCache()
        {
            try
            {
                if (!File.Exists(CacheFile) || new FileInfo(CacheFile).Length > 256L * 1024 * 1024) return;
                var doc = Json.Parse(File.ReadAllText(CacheFile, Encoding.UTF8));
                if (doc.Kind != JsonKind.Object) return;
                foreach (var m in doc.Members)
                    if (m.Value.Kind == JsonKind.Array) guids[m.Key] = m.Value.Items.ConvertAll(v => v.Text ?? "").FindAll(g => g.Length == 32).ToArray();
            }
            catch (Exception) { /* a damaged cache is just read again */ }
        }

        void SaveCache()
        {
            try
            {
                var root = new JsonValue { Kind = JsonKind.Object, Members = new List<KeyValuePair<string, JsonValue>>() };
                foreach (var kv in guids)
                {
                    var arr = new JsonValue { Kind = JsonKind.Array, Items = new List<JsonValue>() };
                    foreach (string g in kv.Value) arr.Items.Add(new JsonValue { Kind = JsonKind.String, Text = g });
                    root.Members.Add(new KeyValuePair<string, JsonValue>(kv.Key, arr));
                }
                Directory.CreateDirectory(Path.GetDirectoryName(CacheFile));
                File.WriteAllBytes(CacheFile, Json.Canonical(root));
                cacheDirty = false;
            }
            catch (Exception) { /* next time, then */ }
        }
    }
}

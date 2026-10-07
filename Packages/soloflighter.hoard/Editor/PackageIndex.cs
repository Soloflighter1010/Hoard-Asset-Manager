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
        // -2: files only (the first kept folders' GUIDs too, which a product shares with others in the same folder)
        static readonly string CacheFile = Path.Combine("Library", "Hoard", "package-guids-2.json");
        readonly ConcurrentDictionary<string, string[]> guids = new ConcurrentDictionary<string, string[]>();   // "path|size|time" -> GUIDs
        struct Counted { public InProject Status; public int Have, Total; }
        readonly Dictionary<string, Counted> status = new Dictionary<string, Counted>();   // path -> how much is here, until something changes
        readonly ConcurrentQueue<string> waiting = new ConcurrentQueue<string>();
        readonly ConcurrentQueue<string> fresh = new ConcurrentQueue<string>();   // read since the last look
        readonly CancellationTokenSource stop = new CancellationTokenSource();
        int queued, done;
        volatile bool changed, cacheDirty;
        DateTime saveAfter = DateTime.MinValue;

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
            // One reader at a time: kind to the disk. A package queued just as the reader finished (after its last
            // look at the queue, before it let go) found it still busy and didn't start one: so it looks again once
            // it has let go, rather than leave that package waiting for good.
            do
            {
                if (Interlocked.Exchange(ref working, 1) == 1) return;
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
                                var found = UnityPackageReader.ReadFiles(path);   // not its folders (shared with other products)
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
            } while (!stop.IsCancellationRequested && !waiting.IsEmpty);
        }

        static string SafeStamp(string path) { try { return Stamp(path); } catch (Exception) { return path; } }

        /// <summary>Call from the editor's update loop: true when there's something new to show. The packages read
        /// since the last call are added to fresh (when given), so only their products need looking at again.</summary>
        public bool TakeChanges(List<string> freshPaths = null)
        {
            if (cacheDirty && Waiting == 0 && DateTime.UtcNow >= saveAfter) SaveCache();
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

        /// <summary>How much of the package the project has. Main thread only. Worked out once, and kept until the
        /// project or the package changes (the window asks on every repaint).</summary>
        public InProject Status(string path, out int have, out int total)
        {
            have = total = 0;
            if (path == null) return InProject.Unknown;
            Counted c;
            if (!status.TryGetValue(path, out c))
            {
                c = Count(path);
                if (c.Status != InProject.Unknown || guids.ContainsKey(SafeStamp(path))) status[path] = c;   // (not yet read: asked again)
            }
            have = c.Have;
            total = c.Total;
            return c.Status;
        }

        Counted Count(string path)
        {
            var c = new Counted { Status = InProject.Unknown };
            string[] list;
            if (!File.Exists(path) || !guids.TryGetValue(Stamp(path), out list)) return c;
            ProjectShare.Count(list, AssetDatabase.GUIDToAssetPath, out c.Have, out c.Total);   // Assets/ only (issue #114)
            if (c.Total > 0) c.Status = c.Have == 0 ? InProject.No : c.Have == c.Total ? InProject.Yes : InProject.Partly;
            return c;
        }

        public InProject Status(string path)
        {
            int have, total;
            return Status(path, out have, out total);
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
                var root = JsonBuild.Obj();
                foreach (var kv in guids)
                    JsonBuild.Put(root, kv.Key, JsonBuild.Arr(new List<string>(kv.Value).ConvertAll(JsonBuild.Str)));
                JsonBuild.WriteFile(CacheFile, Json.Canonical(root));
                cacheDirty = false;
            }
            catch (Exception) { saveAfter = DateTime.UtcNow.AddMinutes(1); }   // can't be written now: tried again in a minute, not every tick
        }
    }
}

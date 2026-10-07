// What this project imported through Hoard, kept in ProjectSettings/Hoard/imports.json so it travels with the
// project (and with version control). One entry per import: which product, which file, and when.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using UnityEditor;

namespace SoloFlighter.Hoard.Editor
{
    public static class ImportLog
    {
        static readonly string LogFile = Path.Combine("ProjectSettings", "Hoard", "imports.json");

        public sealed class Entry
        {
            public string Store, Name, Creator, File, ImportedAt;
        }

        public static List<Entry> Read()
        {
            bool readable;
            return Read(out readable);
        }

        /// <summary>The log; readable is false when there is one that couldn't be read (damaged, or too large), which
        /// Record then keeps aside rather than writing over.</summary>
        static List<Entry> Read(out bool readable)
        {
            var list = new List<Entry>();
            readable = true;
            try
            {
                if (!System.IO.File.Exists(LogFile)) return list;
                if (new FileInfo(LogFile).Length > 16L * 1024 * 1024) { readable = false; return list; }
                var doc = Json.Parse(System.IO.File.ReadAllText(LogFile, Encoding.UTF8));
                var items = doc.Get("imports");
                if (items == null || items.Kind != JsonKind.Array) { readable = false; return list; }
                foreach (var v in items.Items)
                    if (v.Kind == JsonKind.Object)
                        list.Add(new Entry { Store = v.Str("store"), Name = v.Str("name"), Creator = v.Str("creator"),
                                             File = v.Str("file"), ImportedAt = v.Str("imported_at") });
            }
            catch (Exception) { readable = false; list.Clear(); }
            return list;
        }

        public static void Record(HoardAsset asset, string file) { Record(asset.Store, asset.Name, asset.Creator, file); }

        public static void Record(string store, string name, string creator, string file)
        {
            bool readable;
            var list = Read(out readable);
            if (!readable)   // kept beside it, not written over: the project's history isn't lost to one bad edit
                System.IO.File.Move(LogFile, LogFile + ".unreadable-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss", CultureInfo.InvariantCulture));
            list.Add(new Entry { Store = store, Name = name, Creator = creator, File = file,
                                 ImportedAt = DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture) });
            var sb = new StringBuilder("{\n  \"format\": \"hoard-unity-imports\",\n  \"version\": 1,\n  \"imports\": [\n");
            for (int n = 0; n < list.Count; n++)
            {
                var e = list[n];
                sb.Append("    {\"store\": ").Append(Q(e.Store)).Append(", \"name\": ").Append(Q(e.Name))
                  .Append(", \"creator\": ").Append(Q(e.Creator)).Append(", \"file\": ").Append(Q(e.File))
                  .Append(", \"imported_at\": ").Append(Q(e.ImportedAt)).Append(n < list.Count - 1 ? "},\n" : "}\n");
            }
            sb.Append("  ]\n}\n");
            JsonBuild.WriteFile(LogFile, new UTF8Encoding(false).GetBytes(sb.ToString()));
        }

        public static bool Imported(HoardAsset asset, List<Entry> log)
        {
            return log.Exists(e => e.Store == asset.Store && e.Name == asset.Name);
        }

        static string Q(string s)
        {
            if (s == null) return "null";
            return Encoding.UTF8.GetString(Json.Canonical(new JsonValue { Kind = JsonKind.String, Text = s }));
        }
    }

    /// <summary>An import started from Hoard's window, until Unity says how it ended. Kept in SessionState, so it
    /// outlives the editor reloading its scripts: a package with scripts reloads them part way through importing, and
    /// the window (and what it remembered) is made anew, so the import was never logged. A reload while one is
    /// pending is the package's scripts coming in, so it's logged then.</summary>
    [InitializeOnLoad]
    public static class PendingImport
    {
        const string Key = "SoloFlighter.Hoard.PendingImport";

        /// <summary>An import ended (done, cancelled or failed), or was logged after a reload: the window looks again.</summary>
        public static event Action Ended;

        static PendingImport()
        {
            AssetDatabase.importPackageCompleted += name => End(name, true);
            AssetDatabase.importPackageCancelled += name => End(name, false);
            AssetDatabase.importPackageFailed += (name, error) =>
            {
                UnityEngine.Debug.LogWarning("Hoard: importing " + name + " failed: " + error);
                End(name, false);
            };
            if (Parts() != null)   // still pending after the scripts reloaded: they came with the import
                EditorApplication.delayCall += () => { string[] p = Parts(); if (p == null) return; Log(p); Finish(); };
        }

        public static bool Active { get { return Parts() != null; } }

        public static void Start(HoardAsset asset, string path)
        {
            SessionState.SetString(Key, string.Join("\n", new[] { path, asset.Store ?? "", asset.Name ?? "", asset.Creator ?? "" }));
        }

        static string[] Parts()
        {
            string[] p = SessionState.GetString(Key, "").Split('\n');
            return p.Length == 4 && p[0].Length > 0 ? p : null;
        }

        static void End(string packageName, bool done)
        {
            string[] p = Parts();
            if (p == null) return;
            if (Path.GetFileNameWithoutExtension(p[0]) != packageName) return;   // another import, not Hoard's
            if (done) Log(p);
            Finish();
        }

        static void Log(string[] p)
        {
            try { ImportLog.Record(p[1], p[2], p[3], Path.GetFileName(p[0])); }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            {
                UnityEngine.Debug.LogWarning("Hoard: couldn't note the import in ProjectSettings/Hoard/imports.json: " + e.Message);
            }
        }

        static void Finish()
        {
            SessionState.EraseString(Key);   // first: whatever happens after, importing is never left paused
            var ended = Ended;
            if (ended != null) ended();
        }
    }
}

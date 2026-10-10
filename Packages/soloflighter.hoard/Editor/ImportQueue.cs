// Import set (Hoard 4.0): a set's packages imported one after another, each through Unity's own import dialog. Kept
// in SessionState, like PendingImport, so it carries on after a package's scripts make the editor reload its own.
using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;

namespace SoloFlighter.Hoard.Editor
{
    [InitializeOnLoad]
    public static class ImportQueue
    {
        const string Key = "SoloFlighter.Hoard.ImportQueue", TotalKey = "SoloFlighter.Hoard.ImportQueueTotal";

        public struct Item { public string Path, Store, Name, Creator; }

        static ImportQueue()
        {
            PendingImport.Ended += () => { if (Active) EditorApplication.delayCall += Next; };
        }

        public static bool Active { get { return Left > 0; } }
        public static int Left { get { return Read().Count; } }
        public static int Total { get { return SessionState.GetInt(TotalKey, 0); } }

        /// <summary>Import these, in this order: the first now, each next one when the last import ends (imported,
        /// cancelled or failed: a package you cancel is skipped, not the rest).</summary>
        public static void Start(List<Item> items)
        {
            if (items.Count == 0) return;
            Write(items);
            SessionState.SetInt(TotalKey, items.Count);
            Next();
        }

        public static void Stop() { SessionState.EraseString(Key); SessionState.EraseInt(TotalKey); }

        static void Next()
        {
            if (PendingImport.Active) return;   // one at a time: this is called again when that one ends
            var items = Read();
            while (items.Count > 0)
            {
                var it = items[0];
                items.RemoveAt(0);
                Write(items);
                if (!PackageFile.Exists(it.Path)) continue;   // gone since: on to the next
                string file;
                try
                {
                    if (PackageFile.IsZipped(it.Path)) EditorUtility.DisplayProgressBar("Hoard", "Unpacking " + PackageFile.Name(it.Path) + " from its .zip", 0.5f);
                    file = PackageFile.ForImport(it.Path, Path.Combine("Library", "Hoard", "Unzipped"));
                }
                catch (Exception e)
                {
                    UnityEngine.Debug.LogWarning("Hoard: " + PackageFile.Name(it.Path) + " couldn't be unpacked from its .zip (" + e.Message + "), so it was skipped.");
                    continue;
                }
                finally { EditorUtility.ClearProgressBar(); }
                PendingImport.Start(new HoardAsset { Store = it.Store, Name = it.Name, Creator = it.Creator }, file);
                AssetDatabase.ImportPackage(file, true);   // Unity's own dialog: you choose what comes in
                return;
            }
            Stop();
        }

        static List<Item> Read()
        {
            var list = new List<Item>();
            string raw = SessionState.GetString(Key, "");
            if (raw.Length == 0) return list;
            foreach (string line in raw.Split('\n'))
            {
                string[] p = line.Split('\t');
                if (p.Length == 4 && p[0].Length > 0) list.Add(new Item { Path = p[0], Store = p[1], Name = p[2], Creator = p[3] });
            }
            return list;
        }

        static void Write(List<Item> items)
        {
            var lines = items.ConvertAll(i => string.Join("\t", new[] { i.Path, i.Store ?? "", Clean(i.Name), Clean(i.Creator) }));
            if (lines.Count == 0) SessionState.EraseString(Key); else SessionState.SetString(Key, string.Join("\n", lines.ToArray()));
        }

        static string Clean(string s) { return (s ?? "").Replace('\t', ' ').Replace('\n', ' '); }
    }
}

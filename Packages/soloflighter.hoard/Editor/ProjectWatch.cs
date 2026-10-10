// Which changes to the project can change what the Hoard window shows (Hoard 4.0). How much of a product is in the
// project, and what it needs that's missing, depend only on whether the files Hoard knows of are here, and where:
// not on what's in them. So a change that only edits files that were already here (a material saved, Poiyomi
// locking it), or that only touches files no product has, or Poiyomi's OptimizedShaders folders (made again on each
// lock, deleted on unlock), is let pass, rather than have the window work everything out again and tell Hoard.
using System;
using System.Collections.Generic;
using UnityEditor;

namespace SoloFlighter.Hoard.Editor
{
    public sealed class ProjectWatch : AssetPostprocessor
    {
        const double Window = 5;   // seconds: a change Unity reported this long ago is no longer the one projectChanged means

        /// <summary>Does this GUID's being here change what's shown? Set by the Hoard window while it's open; with no
        /// window, every change counts.</summary>
        public static Func<string, bool> Matters;

        static readonly HashSet<string> present = new HashSet<string>(StringComparer.Ordinal);   // seen here, since the last change that counted
        static double reportedAt = -1;
        static bool counts;

        /// <summary>A file's project path (as AssetDatabase.GUIDToAssetPath), remembering the ones that are here: a
        /// later change that only edits them is then known not to change anything shown.</summary>
        public static string PathOf(string guid)
        {
            string path = AssetDatabase.GUIDToAssetPath(guid);
            if (!string.IsNullOrEmpty(path)) present.Add(guid);
            return path;
        }

        static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            double now = EditorApplication.timeSinceStartup;
            if (now - reportedAt > 1) counts = false;   // a new round of changes (Unity may report one in several parts)
            reportedAt = now;
            if (counts) return;
            counts = Counts(imported, deleted, moved, movedFrom);
            if (counts) present.Clear();
        }

        static bool Counts(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            var matters = Matters;
            foreach (string p in deleted)
                if (!ProjectShare.IsRegenerated(p)) return true;   // (its GUID can't be asked once it's gone)
            for (int i = 0; i < moved.Length; i++)
            {
                if (ProjectShare.IsRegenerated(moved[i]) && ProjectShare.IsRegenerated(i < movedFrom.Length ? movedFrom[i] : null)) continue;
                string g = AssetDatabase.AssetPathToGUID(moved[i]);
                if (matters == null || matters(g)) return true;   // in Assets/ or not is part of what's counted
            }
            foreach (string p in imported)
            {
                if (ProjectShare.IsRegenerated(p)) continue;
                string g = AssetDatabase.AssetPathToGUID(p);
                if (present.Contains(g)) continue;                 // here before: only what's in it changed
                if (matters == null || matters(g)) return true;    // new here, and a file Hoard knows of
            }
            return false;
        }

        /// <summary>For EditorApplication.projectChanged: does the change it's telling of count? True unless Unity has
        /// just reported the changes, and none of them can change what's shown.</summary>
        public static bool LastChangeCounts()
        {
            if (reportedAt < 0 || EditorApplication.timeSinceStartup - reportedAt > Window) return true;
            return counts;
        }
    }
}

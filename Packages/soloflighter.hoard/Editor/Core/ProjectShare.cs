// How much of a product's package a project has (Hoard's issue #114). Only what's under Assets/ counts: a package
// often carries its own copy of something VCC installs under Packages/ (Poiyomi, VRCFury, the VRChat SDK), and Unity
// finds those files there by the same GUIDs, so counting them made products look imported when they weren't. Files
// the project has under Packages/ are left out altogether: they're another package's, not this product's. Plain C#.
using System;
using System.Collections.Generic;

namespace SoloFlighter.Hoard
{
    /// <summary>How much of each product a project has, by the GUIDs of its packages' files.</summary>
    public static class ProjectShare
    {
        /// <summary>Of a package's GUIDs, how many this project has under Assets/ (have) out of how many could be
        /// this product's (total). pathOf is the project's path for a GUID, or empty when it has none.</summary>
        public static void Count(IEnumerable<string> guids, Func<string, string> pathOf, out int have, out int total)
        {
            have = total = 0;
            foreach (string g in guids)
            {
                string path = pathOf(g) ?? "";
                if (path.Length == 0) total++;                          // not in the project
                else if (InAssets(path)) { have++; total++; }           // in the project, as this product's
                // else under Packages/ (or elsewhere): another package's file, not counted
            }
        }

        /// <summary>How much of a package the project has (issue #188): 2, all of it, or all but a few files of a big
        /// one (a sample scene or a read-me you deleted); 1, part of it: enough of its own files that it isn't
        /// chance; 0, none, or only a stray file or two of a big package, which another product could have brought
        /// (a texture or a script both carry).</summary>
        public static int Level(int have, int total)
        {
            if (total <= 0 || have <= 0) return 0;
            if (have >= total || (total >= 20 && have * 100 >= total * 95)) return 2;
            if (total <= 3) return 1;
            return have >= 2 && have * 10 >= total ? 1 : 0;
        }

        /// <summary>Issue #189: what taking a product out of the project removes, its project paths in Assets/: the
        /// files of its packages the project has, but not one another product in the project also carries (theirs:
        /// the files of the other products here, a creator's shared shader say), so they keep working.</summary>
        public static List<string> Removable(IEnumerable<string> guids, ICollection<string> theirs, Func<string, string> pathOf)
        {
            var paths = new SortedSet<string>(StringComparer.Ordinal);
            foreach (string g in guids)
            {
                if (theirs != null && theirs.Contains(g)) continue;
                string path = (pathOf(g) ?? "").Replace('\\', '/');
                if (InAssets(path)) paths.Add(path);
            }
            return new List<string>(paths);
        }

        /// <summary>The folders a removal leaves empty, deepest first, up to (not including) Assets/ itself: the
        /// product's own folders. isEmpty tells whether a folder has nothing left in it once those paths are gone.</summary>
        public static List<string> EmptiedFolders(IEnumerable<string> removed, Func<string, bool> isEmpty)
        {
            var found = new List<string>();
            var asked = new HashSet<string>(StringComparer.Ordinal);
            foreach (string path in removed)
            {
                for (int i = path.LastIndexOf('/'); i > "Assets".Length; i = path.LastIndexOf('/', i - 1))
                {
                    string folder = path.Substring(0, i);
                    if (!asked.Add(folder)) break;   // (looked at already, with what's above it)
                    if (!isEmpty(folder)) break;
                    found.Add(folder);
                }
            }
            found.Sort((a, b) => b.Length != a.Length ? b.Length.CompareTo(a.Length) : string.CompareOrdinal(a, b));
            return found;
        }

        /// <summary>Count, by the files that are the product's own (see SharedFiles).</summary>
        public static void Count(IEnumerable<string> guids, SharedFiles shared, Func<string, string> pathOf, out int have, out int total)
        {
            Count(shared == null ? guids : shared.OwnOf(guids), pathOf, out have, out total);
        }

        /// <summary>Is this a file a tool makes again whenever it likes, so it says nothing about what you imported? Poiyomi
        /// writes a material's locked shader into an OptimizedShaders folder each time the material is locked, and
        /// deletes it when it's unlocked; some creators ship those folders in their packages too.</summary>
        public static bool IsRegenerated(string path)
        {
            if (string.IsNullOrEmpty(path)) return false;
            foreach (string part in path.Split('/', '\\'))
                if (string.Equals(part, "OptimizedShaders", StringComparison.OrdinalIgnoreCase)) return true;
            return false;
        }

        /// <summary>Is this project path inside Assets/?</summary>
        public static bool InAssets(string path)
        {
            return path != null && path.Replace('\\', '/').StartsWith("Assets/", StringComparison.Ordinal);
        }
    }

    /// <summary>Files more than one product carries: a creator's shader or textures in each of their products, or a
    /// product also sold in a bundle. Having them in the project says nothing about which of those products you
    /// imported, so a product is told by the files that are its own. One with nothing of its own (the same package
    /// from another store, or a product that's all in a bundle) is told by all of its files, as before.</summary>
    public sealed class SharedFiles
    {
        readonly Dictionary<string, string> owner = new Dictionary<string, string>();   // GUID -> its product, or null: several

        /// <summary>A product's package's files. True when one of them was another product's until now, so how much
        /// of other products is in the project may have changed too.</summary>
        public bool Add(string product, IEnumerable<string> guids)
        {
            bool changed = false;
            foreach (string g in guids)
            {
                string was;
                if (!owner.TryGetValue(g, out was)) owner[g] = product;
                else if (was != null && was != product) { owner[g] = null; changed = true; }
            }
            return changed;
        }

        /// <summary>Whether a GUID is in more than one product's packages (so it can't say which is in the
        /// project).</summary>
        public bool IsShared(string guid) { string was; return owner.TryGetValue(guid, out was) && was == null; }

        /// <summary>Forget every GUID's product.</summary>
        public void Clear() { owner.Clear(); }

        /// <summary>The files a package is told by: those that are its product's own, or all of them if none are.</summary>
        public List<string> OwnOf(IEnumerable<string> guids)
        {
            var all = new List<string>(guids);
            var own = all.FindAll(g => !IsShared(g));
            return own.Count > 0 ? own : all;
        }
    }
}

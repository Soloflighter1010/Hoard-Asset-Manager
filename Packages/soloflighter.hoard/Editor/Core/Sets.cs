// Your sets (Hoard 4.0, hoard/sets.py): products you group to use together, as catalog.json lists them, and the order
// Import set brings them in. Plain C#, no Unity references.
using System;
using System.Collections.Generic;
using System.Text.RegularExpressions;

namespace SoloFlighter.Hoard
{
    /// <summary>A set from Hoard: its name and its products.</summary>
    public sealed class HoardSet
    {
        public string Name;
        public List<string> Folders = new List<string>();   // its products, by their folder in the catalog
    }

    /// <summary>The order to import a set's products in, and which of each product's packages to import.</summary>
    public static class SetOrder
    {
        /// <summary>The set's products in the order to import them: a product another one needs (an outfit's avatar,
        /// say) before the one that needs it, the rest by name. A loop of needs is broken where it's met.</summary>
        public static List<HoardAsset> Order(List<HoardAsset> members)
        {
            var byFolder = new Dictionary<string, HoardAsset>();
            foreach (var a in members) if (a.Folder != null && !byFolder.ContainsKey(a.Folder)) byFolder[a.Folder] = a;
            var sorted = new List<HoardAsset>(members);
            sorted.Sort((x, y) => string.Compare(x.Name, y.Name, StringComparison.OrdinalIgnoreCase));
            var done = new HashSet<HoardAsset>();
            var visiting = new HashSet<HoardAsset>();
            var order = new List<HoardAsset>();
            Action<HoardAsset> visit = null;
            visit = a =>
            {
                if (done.Contains(a) || visiting.Contains(a)) return;
                visiting.Add(a);
                foreach (var n in a.Needs)
                {
                    HoardAsset needed;
                    if (n.Kind == "product" && n.Folder != null && byFolder.TryGetValue(n.Folder, out needed) && needed != a) visit(needed);
                }
                visiting.Remove(a);
                done.Add(a);
                order.Add(a);
            };
            foreach (var a in sorted) visit(a);
            return order;
        }
    }
    /// <summary>Which of a product's packages Import set brings in (0.8.2). A product's folder often holds every
    /// version it was downloaded in (Rusk_v1.0, Rusk_v1.2): only the newest of each is chosen. Face tracking add-ons
    /// are left out unless asked for, since their animations are named like the avatar's own and import beside them;
    /// a product that's only face tracking keeps its packages.</summary>
    public static class SetPicks
    {
        /// <summary>Why a package was picked: chosen, the only one, or a face tracking one beside the
        /// avatar's.</summary>
        public enum Why { Chosen, Older, FaceTracking }

        /// <summary>A package picked to import, and why.</summary>
        public sealed class Pick
        {
            public string Path;
            public Why Why;
        }

        static readonly Regex FaceTrackingName = new Regex(
            @"face[\s_.-]*track|facial[\s_.-]*track|unified[\s_.-]*expressions|sranipal|(?<![a-z0-9])(ft|vrcft)(?![a-z0-9])|" +
            @"フェイス\s*トラッキング|フェイシャル\s*トラッキング|표정\s*트래킹|페이스\s*트래킹",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
        // a version in a file's name: v1.2, Ver.1.20, version 2, 1.2.3, a date (2024-01-15), or a browser's copy number " (1)"
        static readonly Regex VersionPart = new Regex(
            @"(?<![a-z0-9])(v|ver\.?|version)\s*\d+([._]\d+)*[a-z]?(?![0-9])|(?<![a-z0-9.])\d+(\.\d+)+[a-z]?(?![0-9])|" +
            @"(?<![0-9])20\d\d[-_.]?\d\d[-_.]?\d\d(?![0-9])|\s*\(\d+\)",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
        static readonly Regex Numbers = new Regex(@"\d+");
        static readonly Regex NotWord = new Regex(@"[\W_]+");

        /// <summary>Whether a package's name says it's for face tracking.</summary>
        public static bool IsFaceTracking(string name) { return FaceTrackingName.IsMatch(name ?? ""); }

        /// <summary>A package's name without its version, as the newest of each is picked: "Rusk_v1.2.unitypackage"
        /// and "Rusk 1.3.unitypackage" are both "rusk".</summary>
        public static string Stem(string name)
        {
            string n = name ?? "";
            if (n.EndsWith(".unitypackage", StringComparison.OrdinalIgnoreCase)) n = n.Substring(0, n.Length - ".unitypackage".Length);
            return NotWord.Replace(VersionPart.Replace(n, " "), "").ToLowerInvariant();
        }

        /// <summary>The version a name gives, as numbers to compare (1.10 after 1.9), or null.</summary>
        public static List<int> Version(string name)
        {
            foreach (Match m in VersionPart.Matches(name ?? ""))
            {
                if (m.Value.Trim().StartsWith("(")) continue;   // a copy's number isn't a version
                var parts = new List<int>();
                foreach (Match d in Numbers.Matches(m.Value))
                {
                    int x;
                    parts.Add(int.TryParse(d.Value, out x) ? x : int.MaxValue);
                }
                if (parts.Count > 0) return parts;
            }
            return null;
        }

        /// <summary>Compare two versions, number by number.</summary>
        static int Compare(List<int> a, List<int> b)
        {
            for (int i = 0; i < Math.Max(a.Count, b.Count); i++)
            {
                int x = i < a.Count ? a[i] : 0, y = i < b.Count ? b[i] : 0;
                if (x != y) return x.CompareTo(y);
            }
            return 0;
        }

        /// <summary>Each of the product's packages, and whether Import set brings it in. written: when a package was
        /// downloaded (for the newest, where the names don't say).</summary>
        public static List<Pick> Choose(string product, IList<string> packages, Func<string, DateTime> written)
        {
            var picks = new List<Pick>();
            var groups = new Dictionary<string, List<string>>();
            var order = new List<string>();
            foreach (string p in packages)
            {
                string key = Stem(PackageFile.Name(p));
                if (!groups.ContainsKey(key)) { groups[key] = new List<string>(); order.Add(key); }
                groups[key].Add(p);
            }
            var newest = new HashSet<string>();
            foreach (string key in order)
            {
                string best = null;
                List<int> bestVersion = null;
                DateTime bestTime = DateTime.MinValue;
                foreach (string p in groups[key])
                {
                    var v = VersionOf(p);
                    DateTime t;
                    try { t = written(p); } catch (Exception) { t = DateTime.MinValue; }
                    bool better = best == null;
                    if (!better && v != null && bestVersion != null) { int c = Compare(v, bestVersion); better = c > 0 || (c == 0 && t > bestTime); }
                    else if (!better) better = t > bestTime;
                    if (better) { best = p; bestVersion = v; bestTime = t; }
                }
                newest.Add(best);
            }
            bool allFaceTracking = IsFaceTracking(product);
            if (!allFaceTracking)
            {
                allFaceTracking = true;
                foreach (string p in newest) if (!IsFaceTracking(PackageFile.Label(p))) { allFaceTracking = false; break; }
            }
            foreach (string p in packages)
            {
                var why = !newest.Contains(p) ? Why.Older
                        : !allFaceTracking && IsFaceTracking(PackageFile.Label(p)) ? Why.FaceTracking : Why.Chosen;
                picks.Add(new Pick { Path = p, Why = why });
            }
            return picks;
        }

        // the version its name gives, or the .zip's it came in ("Rusk_v1.2.zip › Rusk.unitypackage")
        static List<int> VersionOf(string package)
        {
            var v = Version(PackageFile.Name(package));
            if (v != null) return v;
            string file, member;
            return PackageFile.Split(package, out file, out member) ? Version(System.IO.Path.GetFileName(file)) : null;
        }
    }
}

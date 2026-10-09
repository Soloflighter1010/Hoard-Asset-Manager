// Which product a project's files came from, and whether a product in the project has a newer download than the
// one imported. Plain C#, no Unity references: the window gives it the packages' GUIDs, dates and statuses.
using System;
using System.Collections.Generic;
using System.Globalization;

namespace SoloFlighter.Hoard
{
    /// <summary>A product some of the asked-about files came from, and how many of them.</summary>
    public sealed class Origin
    {
        public string Product;   // its key in the catalog (Store/Folder)
        public int Count;
    }

    public static class Origins
    {
        /// <summary>The products whose packages carry any of these files, most files first. packages: for each
        /// package Hoard has read, its product (several, one per line, when more than one product lists it) and
        /// its files' GUIDs.</summary>
        public static List<Origin> Of(IEnumerable<string> guids, IEnumerable<KeyValuePair<string, string[]>> packages)
        {
            var wanted = new HashSet<string>(guids);
            var found = new Dictionary<string, HashSet<string>>();
            foreach (var p in packages)
            {
                if (string.IsNullOrEmpty(p.Key) || p.Value == null) continue;
                List<string> here = null;
                foreach (string g in p.Value)
                    if (wanted.Contains(g)) (here ?? (here = new List<string>())).Add(g);
                if (here == null) continue;
                foreach (string product in p.Key.Split('\n'))
                {
                    HashSet<string> set;
                    if (!found.TryGetValue(product, out set)) found[product] = set = new HashSet<string>();
                    set.UnionWith(here);
                }
            }
            var list = new List<Origin>();
            foreach (var kv in found) list.Add(new Origin { Product = kv.Key, Count = kv.Value.Count });
            list.Sort((a, b) => a.Count != b.Count ? b.Count.CompareTo(a.Count) : string.CompareOrdinal(a.Product, b.Product));
            return list;
        }
    }

    /// <summary>One of a product's packages: when it was downloaded, and whether the project has all of it.</summary>
    public sealed class PackageState
    {
        public string Path;
        public DateTime Written;   // UTC: Hoard leaves a download's date as when it was saved
        public bool AllHere;
    }

    public static class Updates
    {
        /// <summary>Packages downloaded this long apart are the same download, not an update: a product's packages
        /// come down one after another in one run.</summary>
        public static readonly TimeSpan SameDownload = TimeSpan.FromHours(1);

        /// <summary>A product's package that's a newer download than what the project has, or null: the newest
        /// package not all in the project, when it was downloaded after a package that is (by more than
        /// SameDownload), or after the product was last imported through Hoard.</summary>
        public static string NewerPackage(IList<PackageState> packages, DateTime? lastImport)
        {
            PackageState newest = null;
            foreach (var p in packages)
                if (!p.AllHere && (newest == null || p.Written > newest.Written)) newest = p;
            if (newest == null) return null;
            foreach (var p in packages)
                if (p.AllHere && newest.Written - p.Written > SameDownload) return newest.Path;
            if (lastImport.HasValue && newest.Written > lastImport.Value) return newest.Path;
            return null;
        }

        /// <summary>How the app's update list and the catalog name the same product: its store (any case, "Itch"
        /// is "itch") and its name.</summary>
        public static string Key(string store, string name)
        {
            return (store ?? "").ToLowerInvariant() + "\n" + (name ?? "").Trim();
        }

        /// <summary>What Hoard's last check for updates found, from asset-updates.json in Hoard's app data: for
        /// each product with an update waiting, how many new or changed files. Only ever a hint, so anything
        /// unreadable is just nothing.</summary>
        public static Dictionary<string, int> ReadPending(string json)
        {
            var found = new Dictionary<string, int>();
            try
            {
                var doc = Json.Parse(json);
                var items = doc.Get("items");
                if (items == null || items.Kind != JsonKind.Object) return found;
                foreach (var m in items.Members)
                {
                    var e = m.Value;
                    if (e.Kind != JsonKind.Object) continue;
                    string store = e.Str("store"), name = e.Str("name");
                    var files = e.Get("files");
                    int n = files != null && files.Kind == JsonKind.Array ? files.Items.Count : 0;
                    if (!string.IsNullOrEmpty(store) && !string.IsNullOrEmpty(name) && n > 0) found[Key(store, name)] = n;
                }
            }
            catch (Exception) { found.Clear(); }
            return found;
        }

        /// <summary>When an import was noted in imports.json ("2026-10-08T12:00:00Z"), or null.</summary>
        public static DateTime? ParseTime(string text)
        {
            DateTime t;
            return DateTime.TryParseExact(text ?? "", "yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture,
                                          DateTimeStyles.AdjustToUniversal | DateTimeStyles.AssumeUniversal, out t) ? t : (DateTime?)null;
        }
    }
}

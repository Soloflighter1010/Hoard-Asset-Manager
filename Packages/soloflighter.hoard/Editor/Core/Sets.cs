// Your sets (Hoard 4.0, hoard/sets.py): products you group to use together, as catalog.json lists them, and the order
// Import set brings them in. Plain C#, no Unity references.
using System;
using System.Collections.Generic;

namespace SoloFlighter.Hoard
{
    public sealed class HoardSet
    {
        public string Name;
        public List<string> Folders = new List<string>();   // its products, by their folder in the catalog
    }

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
}

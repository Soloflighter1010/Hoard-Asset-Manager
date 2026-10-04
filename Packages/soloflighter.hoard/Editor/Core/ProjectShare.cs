// How much of a product's package a project has (Hoard's issue #114). Only what's under Assets/ counts: a package
// often carries its own copy of something VCC installs under Packages/ (Poiyomi, VRCFury, the VRChat SDK), and Unity
// finds those files there by the same GUIDs, so counting them made products look imported when they weren't. Files
// the project has under Packages/ are left out altogether: they're another package's, not this product's. Plain C#.
using System;
using System.Collections.Generic;

namespace SoloFlighter.Hoard
{
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

        /// <summary>Is this project path inside Assets/?</summary>
        public static bool InAssets(string path)
        {
            return path != null && path.Replace('\\', '/').StartsWith("Assets/", StringComparison.Ordinal);
        }
    }
}

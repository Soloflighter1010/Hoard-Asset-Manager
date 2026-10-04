// Text that fits the width it's given: cut with "…" rather than clipped part way through a letter, or wrapped part
// way through a word. Plain C#, no Unity references: the window passes in how wide a piece of text is drawn.
using System;

namespace SoloFlighter.Hoard
{
    public static class TextFit
    {
        public const string Ellipsis = "…";

        /// <summary>text, or as much of it as fits in maxWidth with "…" after it. middle: keep the end too
        /// ("CyclopsBe…v1.0.unitypackage"), for a file name, whose version and type are at the end.</summary>
        public static string Fit(string text, float maxWidth, Func<string, float> width, bool middle = false)
        {
            if (string.IsNullOrEmpty(text) || width(text) <= maxWidth) return text ?? "";
            if (width(Ellipsis) > maxWidth) return "";
            int lo = 0, hi = text.Length - 1;   // the most characters kept that still fit (binary search)
            while (lo < hi)
            {
                int mid = (lo + hi + 1) / 2;
                if (width(Cut(text, mid, middle)) <= maxWidth) lo = mid; else hi = mid - 1;
            }
            return Cut(text, lo, middle);
        }

        static string Cut(string text, int keep, bool middle)
        {
            if (!middle) return text.Substring(0, keep).TrimEnd() + Ellipsis;
            int tail = Math.Min((2 * keep + 2) / 3, text.Length), head = keep - tail;   // the end matters more: its type
            return text.Substring(0, head) + Ellipsis + text.Substring(text.Length - tail);
        }
    }
}

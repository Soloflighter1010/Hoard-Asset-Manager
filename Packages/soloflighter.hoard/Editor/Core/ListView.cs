// Which rows of a long list are on screen, so a window only draws those, however long the list.
// Plain C#, no Unity references.
using System;

namespace SoloFlighter.Hoard
{
    public static class ListView
    {
        /// <summary>The first and last row (inclusive) that show in a view viewHeight tall, scrolled to scrollY,
        /// with one spare row either side. last &lt; first when there's nothing to draw.</summary>
        public static void VisibleRange(float scrollY, float viewHeight, float rowHeight, int count, out int first, out int last)
        {
            if (count <= 0 || rowHeight <= 0 || viewHeight <= 0) { first = 0; last = -1; return; }
            first = Math.Max(0, (int)Math.Floor(Math.Max(0f, scrollY) / rowHeight) - 1);
            last = Math.Min(count - 1, (int)Math.Ceiling((Math.Max(0f, scrollY) + viewHeight) / rowHeight));
        }
    }
}

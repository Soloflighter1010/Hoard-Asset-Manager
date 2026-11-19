// Which products' pictures the Hoard window keeps, asks for, and lets go (issue #407). Plain C#, no Unity references:
// ThumbnailCache keeps the textures, and asks this what to do with them.
//
// - A picture drawn in the last KeepDrawn seconds is never let go, however many there are or however much memory they
//   use: letting go of one that's on screen read it again at once, and the window flickered between the picture and
//   its placeholder.
// - A picture that couldn't be read is asked for again after RetryAfter seconds, not never: Hoard may save it a moment
//   later (after the product's download), or the file was being written.
using System.Collections.Generic;

namespace SoloFlighter.Hoard
{
    /// <summary>The pictures kept, most recently drawn first, within a count and a memory budget.</summary>
    public sealed class PictureShelf
    {
        public readonly int Capacity;
        public readonly long Budget;
        public double KeepDrawn = 1.0;     // seconds a drawn picture is never let go
        public double RetryAfter = 30.0;   // seconds before a picture that couldn't be read is asked for again

        /// <summary>A picture kept, or one that couldn't be read: its memory, when it was last drawn, and when it
        /// failed.</summary>
        sealed class Entry { public long Bytes; public double Drawn; public bool Failed; public double FailedAt; }

        readonly Dictionary<string, Entry> kept = new Dictionary<string, Entry>();
        readonly LinkedList<string> recent = new LinkedList<string>();   // most recently drawn first
        readonly Dictionary<string, LinkedListNode<string>> place = new Dictionary<string, LinkedListNode<string>>();
        readonly HashSet<string> asked = new HashSet<string>();
        long used;

        public PictureShelf(int capacity, long budget) { Capacity = capacity; Budget = budget; }

        public long Used { get { return used; } }
        public int Count { get { return kept.Count; } }

        /// <summary>A picture is being drawn now: whether it should be asked for (read from disk). It isn't when it's
        /// kept, already asked for, or couldn't be read less than RetryAfter seconds ago.</summary>
        public bool Drawn(string key, double now)
        {
            Entry e;
            if (kept.TryGetValue(key, out e))
            {
                e.Drawn = now;
                Touch(key);
                if (!e.Failed || now - e.FailedAt < RetryAfter) return false;
                Remove(key);   // (couldn't be read a while ago: tried again)
            }
            return asked.Add(key);
        }

        /// <summary>A picture has been read and made, using bytes of memory.</summary>
        public void Kept(string key, long bytes, double now)
        {
            Remove(key);
            kept[key] = new Entry { Bytes = bytes, Drawn = now };
            used += bytes;
            Touch(key);
        }

        /// <summary>A picture couldn't be read or made.</summary>
        public void Failed(string key, double now)
        {
            Remove(key);
            kept[key] = new Entry { Failed = true, FailedAt = now, Drawn = now };
            Touch(key);
        }

        /// <summary>Whether a picture couldn't be read (and isn't being asked for again yet).</summary>
        public bool HasFailed(string key)
        {
            Entry e;
            return kept.TryGetValue(key, out e) && e.Failed;
        }

        /// <summary>The pictures to let go, least recently drawn first, until the shelf is within its count and budget;
        /// never one drawn in the last KeepDrawn seconds. Each one given is forgotten here.</summary>
        public List<string> ToForget(double now)
        {
            var go = new List<string>();
            var node = recent.Last;
            while (node != null && (kept.Count > Capacity || (used > Budget && kept.Count > 1)))
            {
                var before = node.Previous;
                Entry e;
                if (kept.TryGetValue(node.Value, out e) && now - e.Drawn >= KeepDrawn)
                {
                    go.Add(node.Value);
                    Remove(node.Value);
                }
                node = before;
            }
            return go;
        }

        /// <summary>Forget a picture (it's read again if it's drawn again).</summary>
        public void Remove(string key)
        {
            Entry e;
            if (kept.TryGetValue(key, out e)) { used -= e.Bytes; kept.Remove(key); }
            LinkedListNode<string> node;
            if (place.TryGetValue(key, out node)) { recent.Remove(node); place.Remove(key); }
            asked.Remove(key);
        }

        /// <summary>Forget every picture.</summary>
        public void Clear()
        {
            kept.Clear(); recent.Clear(); place.Clear(); asked.Clear();
            used = 0;
        }

        void Touch(string key)
        {
            LinkedListNode<string> node;
            if (place.TryGetValue(key, out node)) recent.Remove(node);
            place[key] = recent.AddFirst(key);
        }
    }
}

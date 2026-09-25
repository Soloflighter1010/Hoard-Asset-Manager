// Product pictures for the Hoard window, loaded only for rows being drawn: the file is read on a background
// thread, then decoded on Unity's main thread a few per frame, and only the most recently used are kept.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using UnityEngine;

namespace SoloFlighter.Hoard.Editor
{
    public sealed class ThumbnailCache
    {
        const int Capacity = 256;             // pictures kept at once
        const int DecodePerFrame = 6;         // decoded per editor update, so scrolling stays smooth
        const long MaxBytes = 8L * 1024 * 1024;

        readonly Dictionary<string, Texture2D> ready = new Dictionary<string, Texture2D>();   // null: couldn't be shown
        readonly LinkedList<string> recent = new LinkedList<string>();                       // most recently used first
        readonly Dictionary<string, LinkedListNode<string>> place = new Dictionary<string, LinkedListNode<string>>();
        readonly HashSet<string> asked = new HashSet<string>();
        readonly ConcurrentQueue<KeyValuePair<string, byte[]>> read = new ConcurrentQueue<KeyValuePair<string, byte[]>>();

        /// <summary>The picture, or null while it's loading (or when there isn't one).</summary>
        public Texture2D Get(string path)
        {
            if (path == null) return null;
            Texture2D t;
            if (ready.TryGetValue(path, out t)) { Touch(path); return t; }
            if (asked.Add(path))
                Task.Run(() =>
                {
                    byte[] bytes = null;
                    try { if (new FileInfo(path).Length <= MaxBytes) bytes = File.ReadAllBytes(path); }
                    catch (Exception) { bytes = null; }
                    read.Enqueue(new KeyValuePair<string, byte[]>(path, bytes));
                });
            return null;
        }

        /// <summary>Decode a few pictures that have been read. Call from the editor's update; true if any are new.</summary>
        public bool Pump()
        {
            bool any = false;
            KeyValuePair<string, byte[]> item;
            for (int n = 0; n < DecodePerFrame && read.TryDequeue(out item); n++)
            {
                Texture2D t = null;
                if (item.Value != null)
                {
                    t = new Texture2D(2, 2) { hideFlags = HideFlags.HideAndDontSave };
                    if (!t.LoadImage(item.Value)) { UnityEngine.Object.DestroyImmediate(t); t = null; }
                }
                ready[item.Key] = t;
                Touch(item.Key);
                any = true;
            }
            while (recent.Count > Capacity)   // forget the least recently used (it's read again if it's needed)
            {
                string old = recent.Last.Value;
                recent.RemoveLast();
                place.Remove(old);
                asked.Remove(old);
                Texture2D t;
                if (ready.TryGetValue(old, out t) && t != null) UnityEngine.Object.DestroyImmediate(t);
                ready.Remove(old);
            }
            return any;
        }

        void Touch(string path)
        {
            LinkedListNode<string> node;
            if (place.TryGetValue(path, out node)) recent.Remove(node);
            place[path] = recent.AddFirst(path);
        }

        public void Clear()
        {
            foreach (var t in ready.Values) if (t != null) UnityEngine.Object.DestroyImmediate(t);
            ready.Clear();
            recent.Clear();
            place.Clear();
            asked.Clear();
            KeyValuePair<string, byte[]> item;
            while (read.TryDequeue(out item)) { }
        }
    }
}

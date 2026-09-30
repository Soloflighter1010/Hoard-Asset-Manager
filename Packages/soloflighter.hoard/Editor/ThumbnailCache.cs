// Product pictures for the Hoard window, loaded only for rows being drawn: the file is read (and a GIF decoded, every
// frame, at thumbnail size) on a background thread, then made into textures on Unity's main thread a few per frame.
// Only the most recently used are kept, within a memory budget. Animated GIFs play wherever they're drawn.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;

namespace SoloFlighter.Hoard.Editor
{
    public sealed class ThumbnailCache
    {
        const int Capacity = 256;                     // pictures kept at once
        const long Budget = 256L * 1024 * 1024;       // and the memory they may use
        const int DecodePerFrame = 6;                 // made into textures per editor update, so scrolling stays smooth
        const long MaxBytes = 8L * 1024 * 1024;       // a picture file bigger than this isn't read
        const int GifSide = 160;                      // a GIF's frames are kept at most this big: the size it's shown at

        sealed class Picture
        {
            public Texture2D[] Frames;                 // one for a still picture
            public GifImage Timing;                    // null for a still picture
            public long Bytes;
        }

        sealed class Read { public string Path; public byte[] Still; public GifImage Gif; }

        readonly Dictionary<string, Picture> ready = new Dictionary<string, Picture>();   // null: couldn't be shown
        readonly LinkedList<string> recent = new LinkedList<string>();                   // most recently used first
        readonly Dictionary<string, LinkedListNode<string>> place = new Dictionary<string, LinkedListNode<string>>();
        readonly HashSet<string> asked = new HashSet<string>();
        readonly ConcurrentQueue<Read> read = new ConcurrentQueue<Read>();
        long used;
        double animatedDrawnAt = -1;

        /// <summary>The picture (for an animated GIF, the frame showing now), or null while it's loading (or when
        /// there isn't one).</summary>
        public Texture2D Get(string path)
        {
            if (path == null) return null;
            Picture p;
            if (ready.TryGetValue(path, out p))
            {
                Touch(path);
                if (p == null) return null;
                if (p.Timing == null || p.Frames.Length == 1) return p.Frames[0];
                double now = EditorApplication.timeSinceStartup;
                animatedDrawnAt = now;
                return p.Frames[Math.Min(p.Frames.Length - 1, p.Timing.FrameAt(now * 1000))];
            }
            if (asked.Add(path))
                Task.Run(() =>
                {
                    var r = new Read { Path = path };
                    try
                    {
                        if (new FileInfo(path).Length <= MaxBytes)
                        {
                            byte[] bytes = File.ReadAllBytes(path);
                            if (GifDecoder.IsGif(bytes)) r.Gif = GifDecoder.Decode(bytes, GifSide);   // null if it can't be read
                            else r.Still = bytes;
                        }
                    }
                    catch (Exception) { r.Still = null; r.Gif = null; }
                    read.Enqueue(r);
                });
            return null;
        }

        /// <summary>True while an animated picture is on screen, so the window keeps redrawing to play it.</summary>
        public bool Animating { get { return animatedDrawnAt >= 0 && EditorApplication.timeSinceStartup - animatedDrawnAt < 0.5; } }

        /// <summary>Make a few pictures that have been read into textures. Call from the editor's update; true if any
        /// are new.</summary>
        public bool Pump()
        {
            bool any = false;
            Read item;
            for (int n = 0; n < DecodePerFrame && read.TryDequeue(out item); n++)
            {
                var p = Make(item);
                ready[item.Path] = p;
                if (p != null) used += p.Bytes;
                Touch(item.Path);
                any = true;
            }
            while (recent.Count > Capacity || (used > Budget && recent.Count > 1))   // forget the least recently used
            {
                string old = recent.Last.Value;
                recent.RemoveLast();
                place.Remove(old);
                asked.Remove(old);   // it's read again if it's needed
                Picture p;
                if (ready.TryGetValue(old, out p) && p != null) { Destroy(p); used -= p.Bytes; }
                ready.Remove(old);
            }
            return any;
        }

        static Picture Make(Read item)
        {
            if (item.Gif != null)
            {
                var g = item.Gif;
                var frames = new Texture2D[g.Frames.Count];
                for (int i = 0; i < frames.Length; i++)
                {
                    frames[i] = new Texture2D(g.Width, g.Height, TextureFormat.RGBA32, false)
                        { hideFlags = HideFlags.HideAndDontSave, wrapMode = TextureWrapMode.Clamp };
                    frames[i].LoadRawTextureData(g.Frames[i]);
                    frames[i].Apply(false, true);   // no longer readable: its copy in memory is let go
                }
                return new Picture { Frames = frames, Timing = g.Frames.Count > 1 ? g : null, Bytes = (long)g.Width * g.Height * 4 * frames.Length };
            }
            if (item.Still == null) return null;
            var t = new Texture2D(2, 2) { hideFlags = HideFlags.HideAndDontSave };
            if (!t.LoadImage(item.Still, true)) { UnityEngine.Object.DestroyImmediate(t); return null; }
            return new Picture { Frames = new[] { t }, Bytes = (long)t.width * t.height * 4 };
        }

        static void Destroy(Picture p)
        {
            foreach (var t in p.Frames) if (t != null) UnityEngine.Object.DestroyImmediate(t);
        }

        void Touch(string path)
        {
            LinkedListNode<string> node;
            if (place.TryGetValue(path, out node)) recent.Remove(node);
            place[path] = recent.AddFirst(path);
        }

        public void Clear()
        {
            foreach (var p in ready.Values) if (p != null) Destroy(p);
            ready.Clear();
            recent.Clear();
            place.Clear();
            asked.Clear();
            used = 0;
            Read item;
            while (read.TryDequeue(out item)) { }
        }
    }
}

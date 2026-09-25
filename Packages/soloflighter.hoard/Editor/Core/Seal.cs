// Checking the seal Hoard puts on its data files (HMAC-SHA256 with the key in Hoard's app-data folder), as
// described in Hoard's docs/DATA-FORMATS.md. Plain C#, no Unity references.
using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace SoloFlighter.Hoard
{
    public enum SealState
    {
        Sealed,     // made by Hoard on this computer, unchanged since
        Unsealed,   // no seal (written by an older Hoard)
        Foreign,    // sealed with another computer's key: can't be checked here
        Changed,    // the seal doesn't match: something other than Hoard edited the file
        NoKey,      // Hoard's key isn't readable, so the seal can't be checked
    }

    public static class Seal
    {
        /// <summary>Hoard's 32-byte key, from integrity.key (hex), or null if it can't be read.</summary>
        public static byte[] ReadKey(string keyFile)
        {
            try
            {
                if (!File.Exists(keyFile) || new FileInfo(keyFile).Length > 256) return null;
                string hex = File.ReadAllText(keyFile, Encoding.ASCII).Trim();
                if (hex.Length != 64) return null;
                var key = new byte[32];
                for (int n = 0; n < 32; n++) key[n] = Convert.ToByte(hex.Substring(n * 2, 2), 16);
                return key;
            }
            catch (Exception) { return null; }
        }

        /// <summary>Every readable key among these files, each once.</summary>
        public static List<byte[]> ReadKeys(IEnumerable<string> keyFiles)
        {
            var keys = new List<byte[]>();
            var seen = new HashSet<string>();
            foreach (string f in keyFiles)
            {
                var k = ReadKey(f);
                if (k != null && seen.Add(KeyId(k))) keys.Add(k);
            }
            return keys;
        }

        public static string KeyId(byte[] key)
        {
            using (var sha = SHA256.Create()) return Hex(sha.ComputeHash(key)).Substring(0, 16);
        }

        public static SealState Check(JsonValue doc, byte[] key)
        {
            return Check(doc, key == null ? new List<byte[]>() : new List<byte[]> { key });
        }

        /// <summary>Check the seal with whichever of these keys it names. All of them are this user account's own
        /// Hoard keys (see HoardLocation.KeyFiles), so any of them is as good as another: a catalog sealed by a Hoard
        /// whose files Windows keeps separately (Microsoft Store Python) is still recognised.</summary>
        public static SealState Check(JsonValue doc, IList<byte[]> keys)
        {
            var seal = doc.Get("integrity");
            if (seal == null || seal.Kind != JsonKind.Object) return SealState.Unsealed;
            if (keys == null || keys.Count == 0) return SealState.NoKey;
            if (seal.Str("alg") != "HMAC-SHA256") return SealState.Changed;
            byte[] key = null;
            foreach (var k in keys) if (k != null && seal.Str("key_id") == KeyId(k)) { key = k; break; }
            if (key == null) return SealState.Foreign;
            var body = new JsonValue { Kind = JsonKind.Object, Members = doc.Members.FindAll(m => m.Key != "integrity") };
            string expected;
            using (var hmac = new HMACSHA256(key)) expected = Hex(hmac.ComputeHash(Json.Canonical(body)));
            return SameText(expected, seal.Str("mac") ?? "") ? SealState.Sealed : SealState.Changed;
        }

        static bool SameText(string a, string b)   // compared in constant time
        {
            if (a.Length != b.Length) return false;
            int diff = 0;
            for (int n = 0; n < a.Length; n++) diff |= a[n] ^ b[n];
            return diff == 0;
        }

        static string Hex(byte[] bytes)
        {
            var sb = new StringBuilder(bytes.Length * 2);
            foreach (byte b in bytes) sb.Append(b.ToString("x2"));
            return sb.ToString();
        }
    }
}

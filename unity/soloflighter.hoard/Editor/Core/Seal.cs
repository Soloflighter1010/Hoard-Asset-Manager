// Checking the seal Hoard puts on its data files (HMAC-SHA256 with the key in Hoard's app-data folder), as
// described in Hoard's docs/DATA-FORMATS.md. Plain C#, no Unity references.
using System;
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

        public static string KeyId(byte[] key)
        {
            using (var sha = SHA256.Create()) return Hex(sha.ComputeHash(key)).Substring(0, 16);
        }

        public static SealState Check(JsonValue doc, byte[] key)
        {
            var seal = doc.Get("integrity");
            if (seal == null || seal.Kind != JsonKind.Object) return SealState.Unsealed;
            if (key == null) return SealState.NoKey;
            if (seal.Str("alg") != "HMAC-SHA256") return SealState.Changed;
            if (seal.Str("key_id") != KeyId(key)) return SealState.Foreign;
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

using System;
using System.Security.Cryptography;
using System.Text;

namespace ScreenWire.Server.Auth
{
    public static class Authenticator
    {
        public static string ComputeHash(byte[] storedHash, byte[] salt)
        {
            // FIX: SHA256.Create() вместо устаревшего SHA256Managed
            using (var sha = SHA256.Create())
            {
                byte[] c = new byte[storedHash.Length + salt.Length];
                Buffer.BlockCopy(storedHash, 0, c, 0, storedHash.Length);
                Buffer.BlockCopy(salt, 0, c, storedHash.Length, salt.Length);
                return BytesToHex(sha.ComputeHash(c));
            }
        }

        public static string ComputeStoredHash(string password)
        {
            using (var sha = SHA256.Create())
                return Convert.ToBase64String(sha.ComputeHash(Encoding.UTF8.GetBytes(password ?? "")));
        }

        public static byte[] GenerateSalt()
        {
            byte[] s = new byte[16];
            #if NET35
                // Для XP единственный вариант
                new RNGCryptoServiceProvider().GetBytes(s);
            #else
                // Современный способ (.NET 6+)
                System.Security.Cryptography.RandomNumberGenerator.Fill(s);
            #endif
            return s;
        }

        private static string BytesToHex(byte[] b)
        {
            var sb = new StringBuilder(b.Length * 2);
            foreach (var x in b) sb.AppendFormat("{0:x2}", x);
            return sb.ToString();
        }
    }
}
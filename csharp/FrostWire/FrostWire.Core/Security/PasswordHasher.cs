using System.Security.Cryptography;
using System.Text;

namespace FuzzCast.Core.Security;

public static class PasswordHasher
{
    public static byte[] ComputeHash(string password)
    {
        if (string.IsNullOrEmpty(password))
            throw new ArgumentException("Password cannot be empty");

        byte[] inputBytes = Encoding.UTF8.GetBytes(password);
        return MD5.HashData(inputBytes);
    }
}
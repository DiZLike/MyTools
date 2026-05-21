using IconFinder.Forms;
using IconFinder.Models;
using IconFinder.Services;

namespace IconFinder.Monitors
{
    public static class UsingMonitor
    {
        public static UsingInfo Info {  get; set; }

        private static string _path = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "Data", "using.json");
        private const int _usingLimit = 5;

        static UsingMonitor()
        {
            if (!File.Exists(_path))
                Info = new UsingInfo();
        }
        public static void Save()
        {
            JsonService.SaveToJson<UsingInfo>(Info, _path);
        }
        public static async Task Load()
        {
            Info = JsonService.LoadFromJson<UsingInfo>(_path);
        }
        public static void CheckUsing()
        {
            if (Info.TotalSaveCount > 0 && Info.TotalSaveCount % _usingLimit == 0)
            {
                ShowDonateForm();
            }
        }
        private static void ShowDonateForm()
        {
            var donateForm = new DonateForm();
            donateForm.Show();
        }
    }
}

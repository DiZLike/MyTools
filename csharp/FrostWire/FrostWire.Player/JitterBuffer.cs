namespace FrostWire.Player;

public class JitterBuffer
{
    private readonly object _lock = new();
    private readonly SortedDictionary<uint, byte[]> _buffer = new();
    private uint _nextSequence;
    private bool _initialized;

    private const int MaxBufferSize = 10; // 200ms при 20ms фреймах

    public void Add(uint sequence, byte[] opusFrame)
    {
        lock (_lock)
        {
            if (!_initialized)
            {
                _nextSequence = sequence;
                _initialized = true;
            }

            // Игнорируем старые пакеты
            if (sequence < _nextSequence && _initialized)
                return;

            // Не храним слишком много
            if (_buffer.Count >= MaxBufferSize)
            {
                // Удаляем самый старый
                var oldest = _buffer.Keys.First();
                _buffer.Remove(oldest);
                _nextSequence = Math.Max(_nextSequence, oldest + 1);
            }

            _buffer[sequence] = opusFrame;
        }
    }

    public byte[]? GetNext()
    {
        lock (_lock)
        {
            if (!_initialized)
                return null;

            if (_buffer.TryGetValue(_nextSequence, out var frame))
            {
                _buffer.Remove(_nextSequence);
                _nextSequence++;
                return frame;
            }

            // Пакет не пришёл — пропускаем (PLC отработает)
            if (_buffer.Count > 0 && _buffer.Keys.First() > _nextSequence)
            {
                _nextSequence++;
                return null; // дырка
            }

            return null;
        }
    }

    public void Clear()
    {
        lock (_lock)
        {
            _buffer.Clear();
            _initialized = false;
            _nextSequence = 0;
        }
    }
}
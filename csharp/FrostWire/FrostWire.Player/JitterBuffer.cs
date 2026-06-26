namespace FrostWire.Player;

public class JitterBuffer
{
    private readonly object _lock = new();
    private readonly SortedDictionary<uint, byte[]> _buffer = new();
    private uint _nextSequence;
    private bool _initialized;

    private const int MaxBufferSize = 10; // 200ms при 20ms фреймах
    private const uint MaxSequenceGap = 100; // Максимально допустимый разрыв в последовательности

    public void Add(uint sequence, byte[] opusFrame)
    {
        lock (_lock)
        {
            if (!_initialized)
            {
                // При первом пакете инициализируем ожидаемую последовательность
                // Но учитываем, что первый пакет может иметь не нулевой sequence
                _nextSequence = sequence;
                _initialized = true;
            }

            // Проверяем на слишком старые пакеты
            if (sequence < _nextSequence)
            {
                // Если пакет пришёл слишком поздно, но всё ещё в пределах окна, сохраняем
                if (_nextSequence - sequence > MaxBufferSize * 2)
                    return; // Слишком старый, игнорируем
            }

            // Защита от слишком большого разрыва (например, после переполнения uint)
            if (_buffer.Count > 0)
            {
                var lastKey = _buffer.Keys.Last();
                if (sequence > lastKey && sequence - lastKey > MaxSequenceGap)
                {
                    // Вероятно, это новый поток, сбрасываем буфер
                    Console.WriteLine($"[JITTER] Large sequence gap detected ({lastKey} -> {sequence}), resetting buffer");
                    Clear();
                    _nextSequence = sequence;
                }
            }

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

            // Пакет не пришёл — проверяем, может быть он уже устарел
            if (_buffer.Count > 0)
            {
                var firstKey = _buffer.Keys.First();

                // Если первый доступный пакет старше ожидаемого, значит мы его пропустили
                if (firstKey < _nextSequence)
                {
                    _buffer.Remove(firstKey);
                    return null;
                }

                // Если есть разрыв, ждём заполнения
                if (firstKey > _nextSequence)
                {
                    // Проверяем, не слишком ли большой разрыв
                    if (firstKey - _nextSequence > MaxBufferSize)
                    {
                        // Слишком большой разрыв, перескакиваем на первый доступный
                        _nextSequence = firstKey;
                        _buffer.Remove(firstKey);
                        return _buffer.TryGetValue(firstKey, out var jumpFrame) ? jumpFrame : null;
                    }

                    // Возвращаем null, чтобы декодер использовал PLC
                    _nextSequence++;
                    return null;
                }
            }

            return null;
        }
    }

    public int QueuedFrames
    {
        get
        {
            lock (_lock)
            {
                return _buffer.Count;
            }
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
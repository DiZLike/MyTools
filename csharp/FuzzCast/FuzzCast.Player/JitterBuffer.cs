namespace FuzzCast.Player;

/// <summary>
/// Jitter-буфер для компенсации нестабильности сети.
/// Работает по принципу: накапливаем N кадров перед началом выдачи,
/// затем выдаём строго по порядку sequence.
/// При отсутствии кадра — отдаём Missing (для PLC/FEC).
/// Никакой симуляции, только реальная работа.
/// </summary>
public class JitterBuffer
{
    private readonly object _lock = new();
    private readonly SortedDictionary<uint, byte[]> _buffer = new();

    private uint _nextSequence;
    private bool _initialized;
    private bool _prebuffering = true;

    private byte[]? _lastFrame; // Последний успешно декодированный кадр (для FEC)
    private byte[]? _nextFrameForFec; // Следующий кадр в буфере (для FEC)

    // Параметры буфера
    private readonly int _targetBufferSize; // Целевой размер в кадрах (для предзаполнения)
    private readonly int _maxBufferSize;    // Максимальный размер (старые кадры отбрасываются)

    // Статистика
    private uint _totalReceived;
    private uint _totalPlayed;
    private uint _totalMissing;
    private uint _totalLate;
    private DateTime _lastStatsReset = DateTime.UtcNow;

    public JitterBuffer(int targetLatencyMs = 60, int maxLatencyMs = 200)
    {
        // Считаем количество кадров исходя из 20мс на кадр
        _targetBufferSize = Math.Max(2, targetLatencyMs / 20);
        _maxBufferSize = Math.Max(_targetBufferSize * 2, maxLatencyMs / 20);

        Console.WriteLine($"[JITTER] Buffer config: target={_targetBufferSize} frames ({targetLatencyMs}ms), max={_maxBufferSize} frames ({maxLatencyMs}ms)");
    }

    /// <summary>
    /// Добавить полученный аудио-кадр в буфер.
    /// </summary>
    public void Add(uint sequence, byte[] opusFrame)
    {
        lock (_lock)
        {
            _totalReceived++;

            // Самый первый пакет — инициализируем буфер
            if (!_initialized)
            {
                _nextSequence = sequence;
                _initialized = true;
                _prebuffering = true;
                Console.WriteLine($"[JITTER] Initialized at sequence {sequence}, prebuffering {_targetBufferSize} frames");
            }

            // Отбрасываем слишком старые пакеты
            if (sequence < _nextSequence)
            {
                _totalLate++;
                return;
            }

            // Защита от безумных разрывов (переподключение итп)
            if (_buffer.Count > 0)
            {
                var lastKey = _buffer.Keys.Last();
                if (sequence > lastKey && sequence - lastKey > 1000)
                {
                    Console.WriteLine($"[JITTER] Huge gap detected ({lastKey} -> {sequence}), resetting buffer");
                    ResetInternal();
                    _nextSequence = sequence;
                }
            }

            // Ограничиваем размер буфера — удаляем самый старый если переполнен
            while (_buffer.Count >= _maxBufferSize)
            {
                var oldestKey = _buffer.Keys.First();
                _buffer.Remove(oldestKey);

                // Если удалили кадр, который ещё не проиграли — обновляем _nextSequence
                if (oldestKey >= _nextSequence)
                {
                    _nextSequence = oldestKey + 1;
                }
            }

            _buffer[sequence] = opusFrame;
            _nextFrameForFec = null; // Инвалидируем кеш
        }
    }

    /// <summary>
    /// Получить следующий кадр для воспроизведения.
    /// </summary>
    public Result GetNext()
    {
        lock (_lock)
        {
            if (!_initialized)
                return new Result { Type = ResultType.Empty };

            // Предзаполнение: не выдаём кадры пока буфер не наполнится
            if (_prebuffering)
            {
                if (_buffer.Count >= _targetBufferSize)
                {
                    _prebuffering = false;
                    Console.WriteLine($"[JITTER] Prebuffering complete, {_buffer.Count} frames ready");
                }
                else
                {
                    return new Result { Type = ResultType.Empty };
                }
            }

            // Ищем строго следующий по порядку кадр
            if (_buffer.TryGetValue(_nextSequence, out var frame))
            {
                _buffer.Remove(_nextSequence);
                _lastFrame = frame;
                _nextFrameForFec = null; // Инвалидируем
                _nextSequence++;
                _totalPlayed++;

                return new Result
                {
                    Type = ResultType.Normal,
                    Data = frame
                };
            }

            // Кадра нет — пропуск
            // Проверяем, не слишком ли много кадров пропущено подряд
            if (_buffer.Count > 0)
            {
                var firstAvailable = _buffer.Keys.First();

                // Если пропущено больше maxBufferSize — догоняем (резкий скачок)
                if (firstAvailable > _nextSequence + _maxBufferSize)
                {
                    Console.WriteLine($"[JITTER] Too many missing frames ({firstAvailable - _nextSequence}), jumping to {firstAvailable}");
                    _nextSequence = firstAvailable;

                    if (_buffer.TryGetValue(firstAvailable, out var jumpFrame))
                    {
                        _buffer.Remove(firstAvailable);
                        _lastFrame = jumpFrame;
                        _nextFrameForFec = null;
                        _nextSequence = firstAvailable + 1;
                        _totalPlayed++;
                        return new Result { Type = ResultType.Normal, Data = jumpFrame };
                    }
                }
            }

            // Обычный пропуск одного кадра
            _totalMissing++;
            _nextSequence++;
            return new Result { Type = ResultType.Missing };
        }
    }

    /// <summary>
    /// Заглянуть на один кадр вперёд (для FEC).
    /// Возвращает следующий кадр после _nextSequence, не удаляя его из буфера.
    /// </summary>
    public byte[]? PeekNextAvailable()
    {
        lock (_lock)
        {
            if (_nextFrameForFec != null)
                return _nextFrameForFec;

            if (_buffer.TryGetValue(_nextSequence, out var frame))
            {
                _nextFrameForFec = frame;
                return frame;
            }

            return null;
        }
    }

    /// <summary>
    /// Установить последний успешно декодированный кадр (используется PLC).
    /// </summary>
    public void SetLastFrame(byte[] frame)
    {
        lock (_lock)
        {
            _lastFrame = frame;
        }
    }

    /// <summary>
    /// Получить последний успешно декодированный кадр.
    /// </summary>
    public byte[]? GetLastFrame()
    {
        lock (_lock)
        {
            return _lastFrame;
        }
    }

    /// <summary>
    /// Количество кадров в буфере.
    /// </summary>
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

    /// <summary>
    /// Находится ли буфер в режиме предзаполнения.
    /// </summary>
    public bool IsPrebuffering
    {
        get
        {
            lock (_lock)
            {
                return _prebuffering;
            }
        }
    }

    /// <summary>
    /// Статистика буфера.
    /// </summary>
    public JitterStats GetStats()
    {
        lock (_lock)
        {
            return new JitterStats
            {
                Received = _totalReceived,
                Played = _totalPlayed,
                Missing = _totalMissing,
                Late = _totalLate,
                BufferSize = _buffer.Count,
                IsPrebuffering = _prebuffering,
                NextSequence = _nextSequence,
                TimeSinceReset = DateTime.UtcNow - _lastStatsReset
            };
        }
    }

    /// <summary>
    /// Полностью очистить буфер.
    /// </summary>
    public void Clear()
    {
        lock (_lock)
        {
            ResetInternal();
            Console.WriteLine("[JITTER] Buffer cleared");
        }
    }

    private void ResetInternal()
    {
        _buffer.Clear();
        _initialized = false;
        _prebuffering = true;
        _nextSequence = 0;
        _lastFrame = null;
        _nextFrameForFec = null;
        _totalReceived = 0;
        _totalPlayed = 0;
        _totalMissing = 0;
        _totalLate = 0;
        _lastStatsReset = DateTime.UtcNow;
    }

    public enum ResultType
    {
        Empty,   // Буфер пуст или в режиме предзаполнения
        Normal,  // Нормальный кадр
        Missing  // Кадр пропущен — нужно PLC/FEC
    }

    public struct Result
    {
        public ResultType Type;
        public byte[]? Data;
    }

    public struct JitterStats
    {
        public uint Received;
        public uint Played;
        public uint Missing;
        public uint Late;
        public int BufferSize;
        public bool IsPrebuffering;
        public uint NextSequence;
        public TimeSpan TimeSinceReset;

        public double LossPercent => Received > 0
            ? (double)(Missing + Late) / Received * 100
            : 0;
    }
}
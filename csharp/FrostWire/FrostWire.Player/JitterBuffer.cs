namespace FuzzCast.Player;

public class JitterBuffer
{
    private readonly object _lock = new();
    private readonly SortedDictionary<uint, byte[]> _buffer = new();
    private uint _nextSequence;
    private bool _initialized;
    private byte[]? _lastFrame;

    private const int MaxBufferSize = 10;
    private const uint MaxSequenceGap = 100;

    // Симуляция нестабильной сети
    private static readonly Random _rng = new();
    private double _lossRate;
    private double _burstProbability;
    private int _burstLength;
    private int _burstCounter;
    private int _jitterMs;
    private bool _simEnabled;

    private readonly Queue<(DateTime time, uint sequence, byte[] data)> _delayQueue = new();

    public void SetSimulation(double lossPercent, int jitterMs = 0, double burstProb = 0.3)
    {
        _lossRate = Math.Clamp(lossPercent, 0, 100) / 100.0;
        _jitterMs = Math.Max(0, jitterMs);
        _burstProbability = Math.Clamp(burstProb, 0, 1);
        _burstLength = 0;
        _burstCounter = 0;
        _simEnabled = _lossRate > 0 || _jitterMs > 0;

        Console.WriteLine($"[SIM] Loss:{lossPercent:F0}% Jitter:{jitterMs}ms Burst:{burstProb:F1}");
    }

    public void Add(uint sequence, byte[] opusFrame)
    {
        if (_simEnabled)
        {
            // Проверяем бёрст потерь
            if (_burstCounter > 0)
            {
                _burstCounter--;
                return;
            }

            // Случайная потеря
            if (_rng.NextDouble() < _lossRate)
            {
                // С вероятностью burstProbability начинаем бёрст
                if (_rng.NextDouble() < _burstProbability)
                {
                    _burstLength = 2 + _rng.Next(5);
                    _burstCounter = _burstLength - 1;
                }
                return;
            }

            // Джиттер — добавляем задержку
            if (_jitterMs > 0)
            {
                int delayMs = _rng.Next(_jitterMs);
                var deliveryTime = DateTime.UtcNow.AddMilliseconds(delayMs);
                lock (_delayQueue)
                {
                    _delayQueue.Enqueue((deliveryTime, sequence, opusFrame));
                }
                return;
            }
        }

        AddToBuffer(sequence, opusFrame);
    }

    public Result GetNext()
    {
        // Достаём просроченные пакеты из очереди задержек
        ProcessDelayQueue();

        lock (_lock)
        {
            if (!_initialized)
                return new Result { Type = ResultType.Empty };

            if (_buffer.TryGetValue(_nextSequence, out var frame))
            {
                _buffer.Remove(_nextSequence);
                _nextSequence++;
                return new Result { Type = ResultType.Normal, Data = frame };
            }

            if (_buffer.Count > 0)
            {
                var firstKey = _buffer.Keys.First();

                if (firstKey < _nextSequence)
                {
                    _buffer.Remove(firstKey);
                    return new Result { Type = ResultType.Empty };
                }

                if (firstKey > _nextSequence)
                {
                    if (firstKey - _nextSequence > MaxBufferSize)
                    {
                        _nextSequence = firstKey;
                        if (_buffer.TryGetValue(firstKey, out var jumpFrame))
                        {
                            _buffer.Remove(firstKey);
                            _nextSequence = firstKey + 1;
                            return new Result { Type = ResultType.Normal, Data = jumpFrame };
                        }
                    }

                    _nextSequence++;
                    return new Result { Type = ResultType.Missing };
                }
            }

            return new Result { Type = ResultType.Empty };
        }
    }

    private void ProcessDelayQueue()
    {
        lock (_delayQueue)
        {
            var now = DateTime.UtcNow;
            while (_delayQueue.Count > 0 && _delayQueue.Peek().time <= now)
            {
                var (_, sequence, data) = _delayQueue.Dequeue();
                AddToBuffer(sequence, data);
            }
        }
    }

    private void AddToBuffer(uint sequence, byte[] opusFrame)
    {
        lock (_lock)
        {
            if (!_initialized)
            {
                _nextSequence = sequence;
                _initialized = true;
            }

            if (sequence < _nextSequence)
            {
                if (_nextSequence - sequence > MaxBufferSize * 2)
                    return;
            }

            if (_buffer.Count > 0)
            {
                var lastKey = _buffer.Keys.Last();
                if (sequence > lastKey && sequence - lastKey > MaxSequenceGap)
                {
                    Console.WriteLine($"[JITTER] Large sequence gap detected ({lastKey} -> {sequence}), resetting buffer");
                    ClearInternal();
                    _nextSequence = sequence;
                }
            }

            if (_buffer.Count >= MaxBufferSize)
            {
                var oldest = _buffer.Keys.First();
                _buffer.Remove(oldest);
                _nextSequence = Math.Max(_nextSequence, oldest + 1);
            }

            _buffer[sequence] = opusFrame;
        }
    }

    public enum ResultType
    {
        Empty,
        Normal,
        Missing
    }

    public struct Result
    {
        public ResultType Type;
        public byte[]? Data;
    }

    public byte[]? PeekNextAvailable()
    {
        ProcessDelayQueue();

        lock (_lock)
        {
            if (_buffer.Count == 0)
                return null;

            if (_buffer.TryGetValue(_nextSequence, out var next))
                return next;

            return null;
        }
    }

    public void SetLastFrame(byte[] frame)
    {
        _lastFrame = frame;
    }

    public byte[]? GetLastFrame()
    {
        return _lastFrame;
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

    public int DelayedFrames
    {
        get
        {
            lock (_delayQueue)
            {
                return _delayQueue.Count;
            }
        }
    }

    public void Clear()
    {
        lock (_lock)
        {
            ClearInternal();
        }
        lock (_delayQueue)
        {
            _delayQueue.Clear();
        }
    }

    private void ClearInternal()
    {
        _buffer.Clear();
        _initialized = false;
        _nextSequence = 0;
        _lastFrame = null;
        _burstCounter = 0;
        _burstLength = 0;
    }
}
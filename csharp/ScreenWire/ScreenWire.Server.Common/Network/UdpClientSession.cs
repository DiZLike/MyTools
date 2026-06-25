using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Threading;

namespace ScreenWire.Server.Network
{
    public class UdpClientSession
    {
        public IPEndPoint Endpoint { get; }
        public IPEndPoint VideoEndpoint { get; set; }
        public int LastSeen { get; set; }
        public bool Authenticated { get; set; }
        public byte[] Salt { get; set; }
        public int Quality { get; set; } = 50;
        public float ReductionRatio { get; set; } = 1;
        public int TargetFps { get; set; } = 10;
        public int LastFrameSent { get; set; }

        public DateTime LastKeyFrameTime = DateTime.MinValue;

        private Thread _frameThread;
        internal volatile bool _frameRunning;

        private ushort _nextMsgId;
        private SortedList<int, List<PendingMsg>> _pendingByTime = new SortedList<int, List<PendingMsg>>();
        private Dictionary<ushort, PendingMsg> _pendingById = new Dictionary<ushort, PendingMsg>();
        private object _lock = new object();
        private volatile bool _retryRunning = true;

        public UdpClientSession(IPEndPoint ep)
        {
            Endpoint = ep;
            LastSeen = Environment.TickCount;
            var retryThread = new Thread(RetryLoop) { IsBackground = true };
            retryThread.Start();
        }

        public void SendWithRetry(Socket socket, byte msgType, byte[] payload)
        {
            ushort id = _nextMsgId++;
            byte[] packet = Protocol.UdpProtocol.CreateCommandPacket(id, msgType, payload);

            var msg = new PendingMsg
            {
                Id = id,
                Packet = packet,
                SendTime = Environment.TickCount,
                Retries = 0,
                Socket = socket
            };

            lock (_lock)
            {
                _pendingById[id] = msg;
                int timeKey = msg.SendTime / 100;
                if (!_pendingByTime.ContainsKey(timeKey))
                    _pendingByTime[timeKey] = new List<PendingMsg>();
                _pendingByTime[timeKey].Add(msg);
            }

            try { socket.SendTo(packet, Endpoint); } catch { }
        }

        private void RetryLoop()
        {
            while (_retryRunning)
            {
                Thread.Sleep(50);
                int now = Environment.TickCount;
                List<PendingMsg> toRetry = new List<PendingMsg>();
                List<ushort> toRemove = new List<ushort>();

                lock (_lock)
                {
                    foreach (var kvp in _pendingByTime)
                    {
                        foreach (var msg in kvp.Value)
                        {
                            int elapsed = unchecked(now - msg.SendTime);
                            if (elapsed > Protocol.UdpProtocol.AckTimeout * (msg.Retries + 1))
                            {
                                if (msg.Retries >= Protocol.UdpProtocol.MaxRetries)
                                    toRemove.Add(msg.Id);
                                else
                                {
                                    msg.Retries++;
                                    toRetry.Add(msg);
                                    msg.SendTime = now;
                                }
                            }
                        }
                    }
                }

                foreach (var msg in toRetry)
                    try { msg.Socket.SendTo(msg.Packet, Endpoint); } catch { }

                lock (_lock)
                {
                    foreach (var id in toRemove) _pendingById.Remove(id);
                }

                if (unchecked((uint)now % 5000) < 50)
                    CleanupOldEntries(now);
            }
        }

        private void CleanupOldEntries(int now)
        {
            lock (_lock)
            {
                var keysToRemove = new List<int>();
                foreach (var kvp in _pendingByTime)
                {
                    kvp.Value.RemoveAll(m => !_pendingById.ContainsKey(m.Id));
                    if (kvp.Value.Count == 0) keysToRemove.Add(kvp.Key);
                }
                foreach (var key in keysToRemove) _pendingByTime.Remove(key);
            }
        }

        public void OnAckReceived(ushort id)
        {
            lock (_lock) { _pendingById.Remove(id); }
        }

        public void Dispose()
        {
            _retryRunning = false;
            StopFrameThread();
            lock (_lock)
            {
                _pendingById.Clear();
                _pendingByTime.Clear();
            }
        }

        public void StartFrameThread(ParameterizedThreadStart callback)
        {
            StopFrameThread();
            _frameRunning = true;
            _frameThread = new Thread(callback) { IsBackground = true };
            _frameThread.Start(this);
        }

        public void StopFrameThread()
        {
            _frameRunning = false;
            if (_frameThread != null)
            {
                _frameThread.Join(1000);
                _frameThread = null;
            }
        }

        private class PendingMsg
        {
            public byte[] Packet;
            public ushort Id;
            public int SendTime;
            public int Retries;
            public Socket Socket;
        }
    }
}
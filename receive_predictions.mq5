//+------------------------------------------------------------------+
//|                                          receive_predictions.mq5 |
//+------------------------------------------------------------------+
#property strict
#include <Zmq/Zmq.mqh>

Context context;
Socket  socket(context, ZMQ_REQ);

// Request loop guard so we don't send twice without receiving
bool     in_flight = false;

int OnInit()
{
   // Optional but helpful: don't linger on shutdown
   socket.setLinger(0);

   // Try connect and report any error
   string endpoint = "tcp://127.0.0.1:5555";
   if(!socket.connect(endpoint))
   {
      PrintFormat("[ZMQ] connect(%s) failed: %s", endpoint, Zmq::errorMessage());
      return(INIT_FAILED);
   }
   PrintFormat("[ZMQ] Connected to %s", endpoint);

   // Fire every second regardless of ticks
   EventSetTimer(1);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   // Enforce strict REQ/REP: send once, then wait for the reply before sending again
   if(in_flight) return;

   // --- Send
   ZmqMsg req("request_prediction"); // true = null-terminated
   bool sent = socket.send(req, /*nowait*/false);
   if(!sent)
   {
      Print("[ZMQ] send failed: ", Zmq::errorMessage());
      return;
   }
   in_flight = true;

   // --- Receive (blocking). If you want a timeout, use raw buffer + set ReceiveTimeout.
   ZmqMsg resp;
   bool ok = socket.recv(resp, /*nowait*/false);
   if(!ok)
   {
      Print("[ZMQ] recv failed: ", Zmq::errorMessage());
      in_flight = false;
      return;
   }

   string prediction = resp.getData();
   Print("[ZMQ] Received prediction: ", prediction);
   in_flight = false;
}

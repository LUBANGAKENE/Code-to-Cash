//+------------------------------------------------------------------+
//|                                                        Trade.mqh |
//|                                                     Andrew Young |
//|                                 http://www.expertadvisorbook.com |
//+------------------------------------------------------------------+

#property copyright "Andrew Young"
#property link      "http://www.expertadvisorbook.com"

/*
 Creative Commons Attribution-NonCommercial 3.0 Unported
 http://creativecommons.org/licenses/by-nc/3.0/

 You may use this file in your own personal projects. You may 
 modify it if necessary. You may even share it, provided the 
 copyright above is present. No commercial use is permitted. 
*/

#define MAX_RETRIES 5       // Max retries on error
#define RETRY_DELAY 3000    // Retry delay in ms

#include <errordescription.mqh>

//+------------------------------------------------------------------+
//| CTrade Class - Open, Close and Modify Orders                     |
//+------------------------------------------------------------------+
class XTrade
{
protected:
    MqlTradeRequest request;

    bool OpenPosition(string pSymbol, ENUM_ORDER_TYPE pType, double pVolume, double pStop = 0, double pProfit = 0, string pComment = NULL);
    bool OpenPending(string pSymbol, ENUM_ORDER_TYPE pType, double pVolume, double pPrice, double pStop = 0, double pProfit = 0, double pStopLimit = 0, datetime pExpiration = 0, string pComment = NULL);
    void LogTradeRequest();

    ulong              magicNumber;
    ulong              deviation;
    ENUM_ORDER_TYPE_FILLING fillType;

public:
    MqlTradeResult result;

    bool Buy(string pSymbol, double pVolume, double pStop = 0, double pProfit = 0, string pComment = NULL);
    bool Sell(string pSymbol, double pVolume, double pStop = 0, double pProfit = 0, string pComment = NULL);
    bool BuyStop(string pSymbol, double pVolume, double pPrice, double pStop = 0, double pProfit = 0, datetime pExpiration = 0, string pComment = NULL);
    bool SellStop(string pSymbol, double pVolume, double pPrice, double pStop = 0, double pProfit = 0, datetime pExpiration = 0, string pComment = NULL);
    bool BuyLimit(string pSymbol, double pVolume, double pPrice, double pStop = 0, double pProfit = 0, datetime pExpiration = 0, string pComment = NULL);
    bool SellLimit(string pSymbol, double pVolume, double pPrice, double pStop = 0, double pProfit = 0, datetime pExpiration = 0, string pComment = NULL);
    bool BuyStopLimit(string pSymbol, double pVolume, double pPrice, double pStopLimit, double pStop = 0, double pProfit = 0, datetime pExpiration = 0, string pComment = NULL);
    bool SellStopLimit(string pSymbol, double pVolume, double pPrice, double pStopLimit, double pStop = 0, double pProfit = 0, datetime pExpiration = 0, string pComment = NULL);

    bool ModifyPosition(string pSymbol, double pStop, double pProfit = 0);
    bool ModifyPending(ulong pTicket, double pPrice, double pStop, double pProfit, datetime pExpiration = 0);
    bool Close(string pSymbol, double pVolume = 0, string pComment = NULL);
    bool Delete(ulong pTicket);

    void MagicNumber(ulong pMagic);
    void Deviation(ulong pDeviation);
    void FillType(ENUM_ORDER_TYPE_FILLING pFill);
};

// Open position
bool XTrade::OpenPosition(string pSymbol, ENUM_ORDER_TYPE pType, double pVolume, double pStop, double pProfit, string pComment)
{
    ZeroMemory(request);
    ZeroMemory(result);

    request.action       = TRADE_ACTION_DEAL;
    request.symbol       = pSymbol;
    request.type         = pType;
    request.sl           = pStop;
    request.tp           = pProfit;
    request.comment      = pComment;
    request.deviation    = deviation;
    request.type_filling = fillType;
    request.magic        = magicNumber;

    // Calculate lot size
    double positionVol = 0;
    long   positionType = WRONG_VALUE;

    if (PositionSelect(pSymbol))
    {
        positionVol  = PositionGetDouble(POSITION_VOLUME);
        positionType = PositionGetInteger(POSITION_TYPE);
    }

    if ((pType == ORDER_TYPE_BUY  && positionType == POSITION_TYPE_SELL) ||
        (pType == ORDER_TYPE_SELL && positionType == POSITION_TYPE_BUY))
    {
        request.volume = pVolume + positionVol;
    }
    else
    {
        request.volume = pVolume;
    }

    // Order loop
    int retryCount = 0, checkCode = 0;

    do
    {
        if (pType == ORDER_TYPE_BUY)
            request.price = SymbolInfoDouble(pSymbol, SYMBOL_ASK);
        else if (pType == ORDER_TYPE_SELL)
            request.price = SymbolInfoDouble(pSymbol, SYMBOL_BID);

        OrderSend(request, result);
        checkCode = CheckReturnCode(result.retcode);

        if (checkCode == CHECK_RETCODE_OK) break;
        else if (checkCode == CHECK_RETCODE_ERROR)
        {
            Alert("Open market order: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));
            LogTradeRequest();
            break;
        }
        else
        {
            Print("Server error detected, retrying...");
            Sleep(RETRY_DELAY);
            retryCount++;
        }
    }
    while (retryCount < MAX_RETRIES);

    if (retryCount >= MAX_RETRIES)
        Alert("Max retries exceeded: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));

    string orderType = CheckOrderType(pType);
    Print("Open ", orderType, " order #", result.order, ": ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode),
          ", Volume: ", result.volume, ", Price: ", result.price, ", Bid: ", result.bid, ", Ask: ", result.ask);

    if (checkCode == CHECK_RETCODE_OK)
    {
        Comment(orderType, " position opened at ", result.price, " on ", pSymbol);
        return true;
    }
    return false;
}

// Open pending order
bool XTrade::OpenPending(string pSymbol, ENUM_ORDER_TYPE pType, double pVolume, double pPrice, double pStop, double pProfit, double pStopLimit, datetime pExpiration, string pComment)
{
    ZeroMemory(request);
    ZeroMemory(result);

    request.action       = TRADE_ACTION_PENDING;
    request.symbol       = pSymbol;
    request.type         = pType;
    request.sl           = pStop;
    request.tp           = pProfit;
    request.comment      = pComment;
    request.price        = pPrice;
    request.volume       = pVolume;
    request.stoplimit    = pStopLimit;
    request.deviation    = deviation;
    request.type_filling = fillType;
    request.magic        = magicNumber;

    if (pExpiration > 0)
    {
        request.expiration = pExpiration;
        request.type_time  = ORDER_TIME_SPECIFIED;
    }
    else
        request.type_time = ORDER_TIME_GTC;

    int retryCount = 0, checkCode = 0;
    do
    {
        OrderSend(request, result);
        checkCode = CheckReturnCode(result.retcode);

        if (checkCode == CHECK_RETCODE_OK) break;
        else if (checkCode == CHECK_RETCODE_ERROR)
        {
            Alert("Open pending order: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));
            LogTradeRequest();
            break;
        }
        else
        {
            Print("Server error detected, retrying...");
            Sleep(RETRY_DELAY);
            retryCount++;
        }
    }
    while (retryCount < MAX_RETRIES);

    if (retryCount >= MAX_RETRIES)
        Alert("Max retries exceeded: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));

    string orderType = CheckOrderType(pType);
    Print("Open ", orderType, " order #", result.order, ": ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode),
          ", Volume: ", result.volume, ", Price: ", request.price,
          ", Bid: ", SymbolInfoDouble(pSymbol, SYMBOL_BID), ", Ask: ", SymbolInfoDouble(pSymbol, SYMBOL_ASK),
          ", SL: ", request.sl, ", TP: ", request.tp,
          ", Stop Limit: ", request.stoplimit, ", Expiration: ", request.expiration);

    if (checkCode == CHECK_RETCODE_OK)
    {
        Comment(orderType, " order opened at ", request.price, " on ", pSymbol);
        return true;
    }
    return false;
}

// Modify position
bool XTrade::ModifyPosition(string pSymbol, double pStop, double pProfit)
{
    ZeroMemory(request);
    ZeroMemory(result);

    request.action = TRADE_ACTION_SLTP;
    request.symbol = pSymbol;
    request.sl     = pStop;
    request.tp     = pProfit;

    int retryCount = 0, checkCode = 0;
    do
    {
        OrderSend(request, result);
        checkCode = CheckReturnCode(result.retcode);

        if (checkCode == CHECK_RETCODE_OK) break;
        else if (checkCode == CHECK_RETCODE_ERROR)
        {
            Alert("Modify position: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));
            LogTradeRequest();
            break;
        }
        else
        {
            Print("Server error detected, retrying...");
            Sleep(RETRY_DELAY);
            retryCount++;
        }
    }
    while (retryCount < MAX_RETRIES);

    if (retryCount >= MAX_RETRIES)
        Alert("Max retries exceeded: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));

    Print("Modify position: ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode),
          ", SL: ", request.sl, ", TP: ", request.tp,
          ", Bid: ", SymbolInfoDouble(pSymbol, SYMBOL_BID),
          ", Ask: ", SymbolInfoDouble(pSymbol, SYMBOL_ASK),
          ", Stop Level: ", SymbolInfoInteger(pSymbol, SYMBOL_TRADE_STOPS_LEVEL));

    if (checkCode == CHECK_RETCODE_OK)
    {
        Comment("Position modified on ", pSymbol, ", SL: ", request.sl, ", TP: ", request.tp);
        return true;
    }
    return false;
}

// Modify pending order
bool XTrade::ModifyPending(ulong pTicket, double pPrice, double pStop, double pProfit, datetime pExpiration)
{
    ZeroMemory(request);
    ZeroMemory(result);

    request.action = TRADE_ACTION_MODIFY;
    request.order  = pTicket;
    request.sl     = pStop;
    request.tp     = pProfit;

    if (pPrice > 0) request.price = pPrice;
    else            request.price = OrderGetDouble(ORDER_PRICE_OPEN);

    if (pExpiration > 0)
    {
        request.expiration = pExpiration;
        request.type_time  = ORDER_TIME_SPECIFIED;
    }
    else
        request.type_time = ORDER_TIME_GTC;

    int retryCount = 0, checkCode = 0;
    do
    {
        OrderSend(request, result);
        checkCode = CheckReturnCode(result.retcode);

        if (checkCode == CHECK_RETCODE_OK) break;
        else if (checkCode == CHECK_RETCODE_ERROR)
        {
            Alert("Modify pending order: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));
            LogTradeRequest();
            break;
        }
        else
        {
            Print("Server error detected, retrying...");
            Sleep(RETRY_DELAY);
            retryCount++;
        }
    }
    while (retryCount < MAX_RETRIES);

    if (retryCount >= MAX_RETRIES)
        Alert("Max retries exceeded: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));

    Print("Modify pending order #", pTicket, ": ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode),
          ", Price: ", OrderGetDouble(ORDER_PRICE_OPEN),
          ", SL: ", request.sl, ", TP: ", request.tp,
          ", Expiration: ", request.expiration);

    if (checkCode == CHECK_RETCODE_OK)
    {
        Comment("Pending order ", pTicket, " modified, Price: ", OrderGetDouble(ORDER_PRICE_OPEN),
                ", SL: ", request.sl, ", TP: ", request.tp);
        return true;
    }
    return false;
}

// Close position
bool XTrade::Close(string pSymbol, double pVolume, string pComment)
{
    ZeroMemory(request);
    ZeroMemory(result);

    request.action       = TRADE_ACTION_DEAL;
    request.symbol       = pSymbol;
    request.deviation    = deviation;
    request.type_filling = fillType;
    request.magic        = magicNumber;

    double closeVol = 0;
    long   openType = WRONG_VALUE;

    if (PositionSelect(pSymbol))
    {
        closeVol = PositionGetDouble(POSITION_VOLUME);
        openType = PositionGetInteger(POSITION_TYPE);
    }
    else
        return false;

    request.volume = (pVolume > 0 && pVolume <= closeVol) ? pVolume : closeVol;

    int retryCount = 0, checkCode = 0;
    do
    {
        if (openType == POSITION_TYPE_BUY)
        {
            request.type  = ORDER_TYPE_SELL;
            request.price = SymbolInfoDouble(pSymbol, SYMBOL_BID);
        }
        else if (openType == POSITION_TYPE_SELL)
        {
            request.type  = ORDER_TYPE_BUY;
            request.price = SymbolInfoDouble(pSymbol, SYMBOL_ASK);
        }

        OrderSend(request, result);
        checkCode = CheckReturnCode(result.retcode);

        if (checkCode == CHECK_RETCODE_OK) break;
        else if (checkCode == CHECK_RETCODE_ERROR)
        {
            Alert("Close position: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));
            LogTradeRequest();
            break;
        }
        else
        {
            Print("Server error detected, retrying...");
            Sleep(RETRY_DELAY);
            retryCount++;
        }
    }
    while (retryCount < MAX_RETRIES);

    if (retryCount >= MAX_RETRIES)
        Alert("Max retries exceeded: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));

    string posType = (openType == POSITION_TYPE_BUY) ? "Buy" : "Sell";
    Print("Close ", posType, " position #", result.order, ": ", result.retcode, " - ",
          TradeServerReturnCodeDescription(result.retcode),
          ", Volume: ", result.volume, ", Price: ", result.price,
          ", Bid: ", result.bid, ", Ask: ", result.ask);

    if (checkCode == CHECK_RETCODE_OK)
    {
        Comment(posType, " position closed on ", pSymbol, " at ", result.price);
        return true;
    }
    return false;
}

// Delete pending order
bool XTrade::Delete(ulong pTicket)
{
    ZeroMemory(request);
    ZeroMemory(result);

    request.action = TRADE_ACTION_REMOVE;
    request.order  = pTicket;

    int retryCount = 0, checkCode = 0;
    do
    {
        OrderSend(request, result);
        checkCode = CheckReturnCode(result.retcode);

        if (checkCode == CHECK_RETCODE_OK) break;
        else if (checkCode == CHECK_RETCODE_ERROR)
        {
            Alert("Delete order: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));
            LogTradeRequest();
            break;
        }
        else
        {
            Print("Server error detected, retrying...");
            Sleep(RETRY_DELAY);
            retryCount++;
        }
    }
    while (retryCount < MAX_RETRIES);

    if (retryCount >= MAX_RETRIES)
        Alert("Max retries exceeded: Error ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));

    Print("Delete order #", pTicket, ": ", result.retcode, " - ", TradeServerReturnCodeDescription(result.retcode));

    if (checkCode == CHECK_RETCODE_OK)
    {
        Comment("Pending order ", pTicket, " deleted");
        return true;
    }
    return false;
}

void XTrade::LogTradeRequest()
{
    Print("MqlTradeRequest - action:", request.action,
          ", comment:", request.comment,
          ", deviation:", request.deviation,
          ", expiration:", request.expiration,
          ", magic:", request.magic,
          ", order:", request.order,
          ", position:", request.position,
          ", position_by:", request.position_by,
          ", price:", request.price,
          ", sl:", request.sl,
          ", stoplimit:", request.stoplimit,
          ", symbol:", request.symbol,
          ", tp:", request.tp,
          ", type:", request.type,
          ", type_filling:", request.type_filling,
          ", type_time:", request.type_time,
          ", volume:", request.volume);
    Print("MqlTradeResult - ask:", result.ask,
          ", bid:", result.bid,
          ", comment:", result.comment,
          ", deal:", result.deal,
          ", order:", result.order,
          ", price:", result.price,
          ", request_id:", result.request_id,
          ", retcode:", result.retcode,
          ", retcode_external:", result.retcode_external,
          ", volume:", result.volume);
}

// Trade opening shortcuts
bool XTrade::Buy(string pSymbol, double pVolume, double pStop, double pProfit, string pComment)
{
    return OpenPosition(pSymbol, ORDER_TYPE_BUY, pVolume, pStop, pProfit, pComment);
}

bool XTrade::Sell(string pSymbol, double pVolume, double pStop, double pProfit, string pComment)
{
    return OpenPosition(pSymbol, ORDER_TYPE_SELL, pVolume, pStop, pProfit, pComment);
}

bool XTrade::BuyLimit(string pSymbol, double pVolume, double pPrice, double pStop, double pProfit, datetime pExpiration, string pComment)
{
    return OpenPending(pSymbol, ORDER_TYPE_BUY_LIMIT, pVolume, pPrice, pStop, pProfit, 0, pExpiration, pComment);
}

bool XTrade::SellLimit(string pSymbol, double pVolume, double pPrice, double pStop, double pProfit, datetime pExpiration, string pComment)
{
    return OpenPending(pSymbol, ORDER_TYPE_SELL_LIMIT, pVolume, pPrice, pStop, pProfit, 0, pExpiration, pComment);
}

bool XTrade::BuyStop(string pSymbol, double pVolume, double pPrice, double pStop, double pProfit, datetime pExpiration, string pComment)
{
    return OpenPending(pSymbol, ORDER_TYPE_BUY_STOP, pVolume, pPrice, pStop, pProfit, 0, pExpiration, pComment);
}

bool XTrade::SellStop(string pSymbol, double pVolume, double pPrice, double pStop, double pProfit, datetime pExpiration, string pComment)
{
    return OpenPending(pSymbol, ORDER_TYPE_SELL_STOP, pVolume, pPrice, pStop, pProfit, 0, pExpiration, pComment);
}

bool XTrade::BuyStopLimit(string pSymbol, double pVolume, double pPrice, double pStopLimit, double pStop, double pProfit, datetime pExpiration, string pComment)
{
    return OpenPending(pSymbol, ORDER_TYPE_BUY_STOP_LIMIT, pVolume, pPrice, pStop, pProfit, pStopLimit, pExpiration, pComment);
}

bool XTrade::SellStopLimit(string pSymbol, double pVolume, double pPrice, double pStopLimit, double pStop, double pProfit, datetime pExpiration, string pComment)
{
    return OpenPending(pSymbol, ORDER_TYPE_SELL_STOP_LIMIT, pVolume, pPrice, pStop, pProfit, pStopLimit, pExpiration, pComment);
}

// Set magic number
void XTrade::MagicNumber(ulong pMagic)
{
    magicNumber = pMagic;
}

// Set deviation
void XTrade::Deviation(ulong pDeviation)
{
    deviation = pDeviation;
}

// Set fill type
void XTrade::FillType(ENUM_ORDER_TYPE_FILLING pFill)
{
    fillType = pFill;
}

// Return code check
int CheckReturnCode(uint pRetCode)
{
    int status;
    switch (pRetCode)
    {
        case TRADE_RETCODE_REQUOTE:
        case TRADE_RETCODE_CONNECTION:
        case TRADE_RETCODE_PRICE_CHANGED:
        case TRADE_RETCODE_TIMEOUT:
        case TRADE_RETCODE_PRICE_OFF:
        case TRADE_RETCODE_REJECT:
        case TRADE_RETCODE_ERROR:
            status = CHECK_RETCODE_RETRY;
            break;
        case TRADE_RETCODE_DONE:
        case TRADE_RETCODE_DONE_PARTIAL:
        case TRADE_RETCODE_PLACED:
        case TRADE_RETCODE_NO_CHANGES:
            status = CHECK_RETCODE_OK;
            break;
        default:
            status = CHECK_RETCODE_ERROR;
    }
    return status;
}

//+------------------------------------------------------------------+
//| Stop Loss & Take Profit Calculation Functions                   |
//+------------------------------------------------------------------+
double BuyStopLoss(string pSymbol, int pStopPoints, double pOpenPrice = 0)
{
    if (pStopPoints <= 0) return 0;
    double openPrice = (pOpenPrice > 0) ? pOpenPrice : SymbolInfoDouble(pSymbol, SYMBOL_ASK);
    double stopLoss = openPrice - pStopPoints * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    return NormalizeDouble(stopLoss, (int)SymbolInfoInteger(pSymbol, SYMBOL_DIGITS));
}

double SellStopLoss(string pSymbol, int pStopPoints, double pOpenPrice = 0)
{
    if (pStopPoints <= 0) return 0;
    double openPrice = (pOpenPrice > 0) ? pOpenPrice : SymbolInfoDouble(pSymbol, SYMBOL_BID);
    double stopLoss = openPrice + pStopPoints * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    return NormalizeDouble(stopLoss, (int)SymbolInfoInteger(pSymbol, SYMBOL_DIGITS));
}

double BuyTakeProfit(string pSymbol, int pProfitPoints, double pOpenPrice = 0)
{
    if (pProfitPoints <= 0) return 0;
    double openPrice = (pOpenPrice > 0) ? pOpenPrice : SymbolInfoDouble(pSymbol, SYMBOL_ASK);
    double takeProfit = openPrice + pProfitPoints * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    return NormalizeDouble(takeProfit, (int)SymbolInfoInteger(pSymbol, SYMBOL_DIGITS));
}

double SellTakeProfit(string pSymbol, int pProfitPoints, double pOpenPrice = 0)
{
    if (pProfitPoints <= 0) return 0;
    double openPrice = (pOpenPrice > 0) ? pOpenPrice : SymbolInfoDouble(pSymbol, SYMBOL_BID);
    double takeProfit = openPrice - pProfitPoints * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    return NormalizeDouble(takeProfit, (int)SymbolInfoInteger(pSymbol, SYMBOL_DIGITS));
}

//+------------------------------------------------------------------+
//| Stop Level Verification                                          |
//+------------------------------------------------------------------+
bool CheckAboveStopLevel(string pSymbol, double pPrice, int pPoints = 10)
{
    double currPrice  = SymbolInfoDouble(pSymbol, SYMBOL_ASK);
    double stopLevel  = SymbolInfoInteger(pSymbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    double stopPrice  = currPrice + stopLevel;
    double addPoints  = pPoints * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    return (pPrice >= stopPrice + addPoints);
}

bool CheckBelowStopLevel(string pSymbol, double pPrice, int pPoints = 10)
{
    double currPrice  = SymbolInfoDouble(pSymbol, SYMBOL_BID);
    double stopLevel  = SymbolInfoInteger(pSymbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    double stopPrice  = currPrice - stopLevel;
    double addPoints  = pPoints * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    return (pPrice <= stopPrice - addPoints);
}

double AdjustAboveStopLevel(string pSymbol, double pPrice, int pPoints = 10)
{
    double currPrice  = SymbolInfoDouble(pSymbol, SYMBOL_ASK);
    double stopLevel  = SymbolInfoInteger(pSymbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    double stopPrice  = currPrice + stopLevel;
    double addPoints  = pPoints * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    if (pPrice > stopPrice + addPoints) return pPrice;
    double newPrice = stopPrice + addPoints;
    Print("Price adjusted above stop level to ", DoubleToString(newPrice));
    return newPrice;
}

double AdjustBelowStopLevel(string pSymbol, double pPrice, int pPoints = 10)
{
    double currPrice  = SymbolInfoDouble(pSymbol, SYMBOL_BID);
    double stopLevel  = SymbolInfoInteger(pSymbol, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    double stopPrice  = currPrice - stopLevel;
    double addPoints  = pPoints * SymbolInfoDouble(pSymbol, SYMBOL_POINT);
    if (pPrice < stopPrice - addPoints) return pPrice;
    double newPrice = stopPrice - addPoints;
    Print("Price adjusted below stop level to ", DoubleToString(newPrice));
    return newPrice;
}

//+------------------------------------------------------------------+
//| Position Information                                             |
//+------------------------------------------------------------------+
string PositionComment(string pSymbol = NULL)
{
    if (pSymbol == NULL) pSymbol = _Symbol;
    return (PositionSelect(pSymbol) ? PositionGetString(POSITION_COMMENT) : NULL);
}

long PositionType(string pSymbol = NULL)
{
    if (pSymbol == NULL) pSymbol = _Symbol;
    return (PositionSelect(pSymbol) ? PositionGetInteger(POSITION_TYPE) : WRONG_VALUE);
}

long PositionIdentifier(string pSymbol = NULL)
{
    if (pSymbol == NULL) pSymbol = _Symbol;
    return (PositionSelect(pSymbol) ? PositionGetInteger(POSITION_IDENTIFIER) : WRONG_VALUE);
}

double PositionOpenPrice(string pSymbol = NULL)
{
    if (pSymbol == NULL) pSymbol = _Symbol;
    return (PositionSelect(pSymbol) ? PositionGetDouble(POSITION_PRICE_OPEN) : WRONG_VALUE);
}

long PositionOpenTime(string pSymbol = NULL)
{
    if (pSymbol == NULL) pSymbol = _Symbol;
    return (PositionSelect(pSymbol) ? PositionGetInteger(POSITION_TIME) : WRONG_VALUE);
}

double PositionVolume(string pSymbol = NULL)
{
    if (pSymbol == NULL) pSymbol = _Symbol;
    return (PositionSelect(pSymbol) ? PositionGetDouble(POSITION_VOLUME) : WRONG_VALUE);
}

double PositionStopLoss(string pSymbol = NULL)
{
    if (pSymbol == NULL) pSymbol = _Symbol;
    return (PositionSelect(pSymbol) ? PositionGetDouble(POSITION_SL) : WRONG_VALUE);
}

double PositionTakeProfit(string pSymbol = NULL)
{
    if (pSymbol == NULL) pSymbol = _Symbol;
    return (PositionSelect(pSymbol) ? PositionGetDouble(POSITION_TP) : WRONG_VALUE);
}

double PositionProfit(string pSymbol = NULL)
{
    if (pSymbol == NULL) pSymbol = _Symbol;
    return (PositionSelect(pSymbol) ? PositionGetDouble(POSITION_PROFIT) : WRONG_VALUE);
}

//+------------------------------------------------------------------+
//| Miscellaneous Functions & Enumerations                           |
//+------------------------------------------------------------------+
enum ENUM_CHECK_RETCODE
{
    CHECK_RETCODE_OK,
    CHECK_RETCODE_ERROR,
    CHECK_RETCODE_RETRY
};

string CheckOrderType(ENUM_ORDER_TYPE pType)
{
    switch (pType)
    {
        case ORDER_TYPE_BUY:            return "buy";
        case ORDER_TYPE_SELL:           return "sell";
        case ORDER_TYPE_BUY_STOP:       return "buy stop";
        case ORDER_TYPE_BUY_LIMIT:      return "buy limit";
        case ORDER_TYPE_SELL_STOP:      return "sell stop";
        case ORDER_TYPE_SELL_LIMIT:     return "sell limit";
        case ORDER_TYPE_BUY_STOP_LIMIT: return "buy stop limit";
        case ORDER_TYPE_SELL_STOP_LIMIT:return "sell stop limit";
        default:                        return "invalid order type";
    }
}

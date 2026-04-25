from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
import numpy as np
from deep_translator import GoogleTranslator

app = FastAPI()

class DCAInput(BaseModel):
    tickers: str # comma separated
    amount: float
    start_date: str
    end_date: str

class TickerResult(BaseModel):
    portfolio: list[float]
    cagr: float
    max_drawdown: float
    final_value: float

class DCAResponse(BaseModel):
    chart_labels: list[str]
    chart_invested: list[float]
    tickers: dict[str, TickerResult]
    # Overall Aggregate
    cagr: float
    max_drawdown: float
    final_value: float
    total_invested: float

@app.get("/api/info")
def get_company_info(tickers: str = Query(...)):
    ticker_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    info_dict = {}
    
    for t in ticker_list:
        try:
            ticker_obj = yf.Ticker(t)
            info = ticker_obj.info
            name = info.get("longName", info.get("shortName", t))
            sector = info.get("sector", "")
            industry = info.get("industry", "")
            country = info.get("country", "")
            market_cap = info.get("marketCap", None)
            full_summary = info.get("longBusinessSummary", "")

            # Build concise Chinese one-liner for header
            parts = []
            if country:
                parts.append(f"位於{country}")
            if sector:
                parts.append(f"屬於{sector}產業")
            if industry:
                parts.append(f"主營{industry}")
            if market_cap:
                mc_b = market_cap / 1e8
                mc_str = f"市值約 {mc_b/10000:.1f} 兆元" if mc_b >= 10000 else f"市值約 {mc_b:.0f} 億元"
                parts.append(mc_str)

            short_intro = ("、".join(parts) + "。") if parts else ""

            # Translate full summary to Traditional Chinese
            # GoogleTranslator has a ~5000 char limit per call, chunk if needed
            translated = ""
            if full_summary:
                try:
                    chunk_size = 4500
                    chunks = [full_summary[i:i+chunk_size] for i in range(0, len(full_summary), chunk_size)]
                    translated = "".join(
                        GoogleTranslator(source='auto', target='zh-TW').translate(chunk)
                        for chunk in chunks
                    )
                except Exception:
                    translated = full_summary  # fallback to original if translation fails
            else:
                translated = "暫無詳細介紹。"

            info_dict[t] = {
                "name": name,
                "sector": sector if sector else (industry if industry else "ETF / 其他"),
                "short_intro": short_intro,
                "summary": translated
            }
        except Exception:
            info_dict[t] = {
                "name": t,
                "sector": "無法取得",
                "short_intro": "",
                "summary": "無法獲取此標的的資料，請確認代號是否正確。"
            }
            
    return {"data": info_dict}


@app.post("/api/calculate", response_model=DCAResponse)
def calculate_dca(data: DCAInput):
    ticker_list = [t.strip().upper() for t in data.tickers.split(",") if t.strip()]
    if not ticker_list:
        raise HTTPException(status_code=400, detail="請輸入至少一個標的。")

    try:
        num_tickers = len(ticker_list)

        # --- Download data for each ticker individually for reliability ---
        all_close: dict[str, pd.Series] = {}
        for t in ticker_list:
            raw = yf.download(t, start=data.start_date, end=data.end_date,
                              progress=False, auto_adjust=True)
            if raw.empty:
                raise HTTPException(status_code=400,
                    detail=f"無法取得 {t} 的資料，請確認代號與日期區間是否正確。")
            # Close column: single ticker always returns flat column
            close = raw["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            all_close[t] = close.ffill().bfill().dropna()

        # Build a common date index (intersection of all tickers)
        common_index = all_close[ticker_list[0]].index
        for t in ticker_list[1:]:
            common_index = common_index.intersection(all_close[t].index)

        if len(common_index) == 0:
            raise HTTPException(status_code=400, detail="所選標的在指定區間內沒有共同的交易日。")

        # Reindex each series to common_index
        for t in ticker_list:
            all_close[t] = all_close[t].reindex(common_index).ffill().bfill()

        # Monthly buy dates: first trading day of each month
        month_groups = pd.Series(common_index).groupby(
            [common_index.year, common_index.month]
        )
        buy_dates = pd.DatetimeIndex([g.iloc[0] for _, g in month_groups])

        if len(buy_dates) == 0:
            raise HTTPException(status_code=400, detail="區間內無交易日。")

        # Per-ticker invested series (same amount each month per ticker)
        invested_series = pd.Series(0.0, index=common_index)
        for d in buy_dates:
            invested_series.loc[d] += float(data.amount)
        cum_per_ticker_invested = invested_series.cumsum()
        cum_total_invested = cum_per_ticker_invested * num_tickers

        overall_portfolio = pd.Series(0.0, index=common_index)
        results = {}

        for t in ticker_list:
            close_prices = all_close[t]
            shares_added = pd.Series(0.0, index=common_index)

            for d in buy_dates:
                if d in close_prices.index:
                    price = float(close_prices.loc[d])
                    if price > 0 and not pd.isna(price):
                        shares_added.loc[d] += data.amount / price

            total_shares = shares_added.cumsum()
            portfolio_values = (total_shares * close_prices).fillna(0)
            overall_portfolio += portfolio_values

            t_final = float(portfolio_values.iloc[-1])
            t_invested = float(cum_per_ticker_invested.iloc[-1])
            t_days = (common_index[-1] - common_index[0]).days
            t_years = max(t_days / 365.25, 1.0 / 12.0)
            t_cagr = ((t_final / t_invested) ** (1 / t_years) - 1) if t_invested > 0 else 0.0

            t_peak = portfolio_values.cummax()
            t_dd = (portfolio_values - t_peak) / t_peak.replace(0, float('nan'))
            t_md = float(t_dd.min()) if not t_dd.dropna().empty else 0.0

            results[t] = TickerResult(
                portfolio=portfolio_values.round(2).tolist(),
                cagr=t_cagr,
                max_drawdown=t_md,
                final_value=t_final
            )

        # Overall portfolio stats
        overall_final = float(overall_portfolio.iloc[-1])
        overall_invested = float(cum_total_invested.iloc[-1])
        years = max((common_index[-1] - common_index[0]).days / 365.25, 1.0 / 12.0)
        overall_cagr = ((overall_final / overall_invested) ** (1 / years) - 1) if overall_invested > 0 else 0.0

        o_peak = overall_portfolio.cummax()
        o_dd = (overall_portfolio - o_peak) / o_peak.replace(0, float('nan'))
        overall_md = float(o_dd.min()) if not o_dd.dropna().empty else 0.0

        return DCAResponse(
            chart_labels=common_index.strftime('%Y-%m-%d').tolist(),
            chart_invested=cum_per_ticker_invested.round(2).tolist(),
            tickers=results,
            cagr=overall_cagr,
            max_drawdown=overall_md,
            final_value=overall_final,
            total_invested=overall_invested
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"計算錯誤：{str(e)}")

# Serve static files for the frontend
import os
os.makedirs("static", exist_ok=True)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

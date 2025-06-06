# epv_valuation_model/epv_calculator.py
# This module performs the core EPV (Earnings Power Value) and Asset Value calculations.
# It uses settings and standardized names from config.py.

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional, Tuple

# Import configurations from config_manager.py
from .config_manager import get_config
# Removed old config imports

def calculate_normalized_ebit(
    income_statement: pd.DataFrame,
    num_years: Optional[int] = None
) -> Optional[Tuple[float, float]]:
    app_config = get_config()
    if num_years is None:
        num_years = app_config.calculation.normalization_years
    """
    Calculates Normalized EBIT (Operating Income).
    Uses average operating margin over `num_years` applied to the latest year's revenue.

    Args:
        income_statement (pd.DataFrame): Processed income statement with years as columns.
                                         Rows should include 'Total Revenue' and 'Operating Income'.
        num_years (int): Number of past years to use for averaging operating margin.

    Returns:
        Optional[Tuple[float, float]]: (normalized_ebit, average_operating_margin), or None if calculation fails.
    """
    print("--- Debug: calculate_normalized_ebit ---")
    print("Income Statement (Head):\n", income_statement.head())
    print("Income Statement Index:\n", income_statement.index.tolist())
    print("Income Statement Columns:\n", income_statement.columns.tolist())
    print("Income Statement dtypes:\n", income_statement.dtypes)
    # Using standardized names from app_config
    if app_config.financial_item_names.s_revenue not in income_statement.index or \
       app_config.financial_item_names.s_operating_income not in income_statement.index:
        print(f"Error: '{app_config.financial_item_names.s_revenue}' or '{app_config.financial_item_names.s_operating_income}' not found in processed income statement.")
        return None
    if income_statement.empty or len(income_statement.columns) == 0:
        print("Error: Income statement is empty or has no data columns.")
        return None

    try:
        relevant_years_df = income_statement.iloc[:, :num_years]
        print("Debug: relevant_years_df (Head):\n", relevant_years_df.head())
        print("Debug: relevant_years_df Index:", relevant_years_df.index.tolist())
        print("Debug: relevant_years_df Columns:", relevant_years_df.columns.tolist())

        op_income = relevant_years_df.loc[app_config.financial_item_names.s_operating_income]
        revenue = relevant_years_df.loc[app_config.financial_item_names.s_revenue]
        # If duplicate index, .loc returns DataFrame; select first row
        if isinstance(op_income, pd.DataFrame):
            print(f"Warning: Duplicate index for {app_config.financial_item_names.s_operating_income}, selecting first row.")
            op_income = op_income.iloc[0]
        if isinstance(revenue, pd.DataFrame):
            print(f"Warning: Duplicate index for {app_config.financial_item_names.s_revenue}, selecting first row.")
            revenue = revenue.iloc[0]
        print(f"Debug: {app_config.financial_item_names.s_operating_income} Series:\n", op_income)
        print(f"Debug: {app_config.financial_item_names.s_revenue} Series:\n", revenue)
        print(f"Debug: Type of {app_config.financial_item_names.s_operating_income} Series:", type(op_income))
        print(f"Debug: Type of {app_config.financial_item_names.s_revenue} Series:", type(revenue))

        operating_margins = op_income / revenue
        print("Debug: Calculated operating_margins Series:\n", operating_margins)
        print("Debug: Type of operating_margins:", type(operating_margins))

        average_operating_margin = operating_margins.mean(skipna=True)
        print("Debug: Calculated average_operating_margin:", average_operating_margin)
        print("Debug: Type of average_operating_margin:", type(average_operating_margin))

        if isinstance(average_operating_margin, pd.Series):
            if average_operating_margin.empty or average_operating_margin.isna().all():
                print("Error: Could not calculate average operating margin (all NaNs or insufficient data in Series).")
                return None
            # If it's a Series but not all NaN, it implies upstream issue. For now, take mean to make scalar.
            # This is a defensive measure; ideally, average_operating_margin should be scalar.
            print("Warning: average_operating_margin is a Series. Taking mean to convert to scalar. Upstream data issue likely.")
            average_operating_margin = average_operating_margin.mean(skipna=True)
            if pd.isna(average_operating_margin): # Re-check after attempting to make it scalar
                 print("Error: Could not calculate average operating margin (scalar result is NaN).")
                 return None
        elif pd.isna(average_operating_margin): # Original check if it's already a scalar
            print("Error: Could not calculate average operating margin (all NaNs or insufficient data).")
            return None

        latest_revenue = revenue.iloc[0]
        print("Debug: Calculated latest_revenue:", latest_revenue)
        print("Debug: Type of latest_revenue:", type(latest_revenue))
        if pd.isna(latest_revenue):
            print("Error: Latest revenue is NaN.")
            return None

        normalized_ebit = latest_revenue * average_operating_margin
        print(f"Normalized EBIT calculated: {normalized_ebit:,.0f} (Avg Op Margin: {average_operating_margin:.2%})")
        return normalized_ebit, average_operating_margin
    except Exception as e:
        print(f"Error calculating normalized EBIT: {e}")
        return None


def calculate_maintenance_capex(
    income_statement: pd.DataFrame,
    balance_sheet: pd.DataFrame,
    cash_flow_statement: pd.DataFrame,
    num_years: Optional[int] = None
) -> Optional[float]:
    app_config = get_config()
    if num_years is None:
        num_years = app_config.calculation.normalization_years
    """
    Calculates Maintenance Capital Expenditures using Greenwald's PPE/Sales method.
    Maintenance Capex = Average (Total Capex - Growth Capex)
    Growth Capex = (Average Gross PPE / Average Sales over N years) * Change in Sales in current year

    Args:
        income_statement (pd.DataFrame): Processed income statement.
        balance_sheet (pd.DataFrame): Processed balance sheet.
        cash_flow_statement (pd.DataFrame): Processed cash flow statement.
        num_years (int): Number of years for averaging PPE/Sales ratio.

    Returns:
        Optional[float]: Estimated maintenance capex, or None if calculation fails.
    """
    required_is_items = [app_config.financial_item_names.s_revenue]
    required_bs_items = [app_config.financial_item_names.s_gross_ppe] # Prefer Gross PPE
    required_cf_items = [app_config.financial_item_names.s_capex]

    if not all(item in income_statement.index for item in required_is_items) or \
       not any(item in balance_sheet.index for item in [app_config.financial_item_names.s_gross_ppe, app_config.financial_item_names.s_net_ppe]) or \
       not all(item in cash_flow_statement.index for item in required_cf_items):
        print("Error: Required items for Maintenance Capex calculation are missing from financial statements.")
        print(f"  Need: {app_config.financial_item_names.s_revenue} (IS), {app_config.financial_item_names.s_gross_ppe} or {app_config.financial_item_names.s_net_ppe} (BS), {app_config.financial_item_names.s_capex} (CF)")
        return None

    try:
        ppe_item_to_use = app_config.financial_item_names.s_gross_ppe if app_config.financial_item_names.s_gross_ppe in balance_sheet.index else app_config.financial_item_names.s_net_ppe
        print(f"Using '{ppe_item_to_use}' for Maintenance Capex calculation.")

        common_cols = income_statement.columns.intersection(balance_sheet.columns).intersection(cash_flow_statement.columns)
        if len(common_cols) < 2:
            print("Error: Insufficient common years across statements for Maintenance Capex calculation.")
            return None

        is_sorted = income_statement[common_cols].sort_index(axis=1, ascending=False)
        bs_sorted = balance_sheet[common_cols].sort_index(axis=1, ascending=False)
        cf_sorted = cash_flow_statement[common_cols].sort_index(axis=1, ascending=False)

        sales_history = is_sorted.loc[app_config.financial_item_names.s_revenue].iloc[:num_years + 1]
        ppe_history = bs_sorted.loc[ppe_item_to_use].iloc[:num_years + 1]
        total_capex_history = cf_sorted.loc[app_config.financial_item_names.s_capex].iloc[:num_years]

        if len(sales_history) < 2 or len(ppe_history) < 1 or len(total_capex_history) < 1:
             print("Error: Not enough historical data points for Maintenance Capex after alignment.")
             return None

        ppe_div_sales_ratios = []
        for i in range(min(num_years, len(sales_history) -1, len(ppe_history) -1)):
            sales_t = sales_history.iloc[i]
            ppe_t_minus_1 = ppe_history.iloc[i+1]
            if pd.notna(sales_t) and sales_t != 0 and pd.notna(ppe_t_minus_1):
                ppe_div_sales_ratios.append(ppe_t_minus_1 / sales_t)

        if not ppe_div_sales_ratios:
            print("Error: Could not calculate any valid PPE/Sales ratios.")
            return None
        avg_ppe_div_sales = np.mean(ppe_div_sales_ratios)
        if pd.isna(avg_ppe_div_sales):
            print("Error: Average PPE/Sales ratio is NaN.")
            return None

        maintenance_capex_values = []
        for i in range(min(num_years, len(sales_history) -1, len(total_capex_history))):
            sales_current_year = sales_history.iloc[i]
            sales_previous_year = sales_history.iloc[i+1]
            current_total_capex = total_capex_history.iloc[i]

            if pd.isna(sales_current_year) or pd.isna(sales_previous_year) or pd.isna(current_total_capex):
                continue
            sales_growth = sales_current_year - sales_previous_year
            growth_capex = avg_ppe_div_sales * sales_growth
            maintenance_capex_estimate = abs(current_total_capex) - growth_capex
            maintenance_capex_values.append(maintenance_capex_estimate)

        if not maintenance_capex_values:
            print("Error: Could not calculate any Maintenance Capex values.")
            if app_config.financial_item_names.s_depreciation_cf in cf_sorted.index:
                avg_depreciation = abs(cf_sorted.loc[app_config.financial_item_names.s_depreciation_cf].iloc[:num_years].mean(skipna=True))
                if pd.notna(avg_depreciation):
                    print(f"Warning: Falling back to average D&A for Maintenance Capex: {avg_depreciation:,.0f}")
                    return avg_depreciation
            return None

        avg_maintenance_capex = np.mean(maintenance_capex_values)
        avg_depreciation_cf_val = abs(cf_sorted.loc[app_config.financial_item_names.s_depreciation_cf].iloc[:num_years].mean(skipna=True)) if app_config.financial_item_names.s_depreciation_cf in cf_sorted.index else None
        
        final_maint_capex = max(0, avg_maintenance_capex)
        if avg_depreciation_cf_val is not None and pd.notna(avg_depreciation_cf_val) and final_maint_capex < avg_depreciation_cf_val * 0.5:
            print(f"Warning: Calculated Avg Maint Capex ({final_maint_capex:,.0f}) is significantly lower than Avg D&A ({avg_depreciation_cf_val:,.0f}). Consider D&A.")

        print(f"Calculated Average Maintenance Capex: {final_maint_capex:,.0f} (using {len(maintenance_capex_values)} year(s) estimates)")
        return final_maint_capex
    except Exception as e:
        print(f"Error calculating maintenance capex: {e}")
        return None

def calculate_nopat(
    normalized_ebit: float,
    income_statement: pd.DataFrame,
    num_years: Optional[int] = None
) -> Optional[float]:
    app_config = get_config()
    if num_years is None:
        num_years = app_config.calculation.normalization_years
    """
    Calculates Net Operating Profit After Tax (NOPAT).
    NOPAT = Normalized EBIT * (1 - Effective Tax Rate)
    Effective Tax Rate is averaged over `num_years`.
    """
    if app_config.financial_item_names.s_tax_provision not in income_statement.index or \
       app_config.financial_item_names.s_pretax_income not in income_statement.index:
        print(f"Error: '{app_config.financial_item_names.s_tax_provision}' or '{app_config.financial_item_names.s_pretax_income}' not found for NOPAT calc.")
        return None

    try:
        relevant_years_df = income_statement.iloc[:, :num_years]
        tax_rates = []
        for col in relevant_years_df.columns:
            tax_prov = relevant_years_df.loc[app_config.financial_item_names.s_tax_provision, col]
            pre_tax_inc = relevant_years_df.loc[app_config.financial_item_names.s_pretax_income, col]
            if pd.notna(tax_prov) and pd.notna(pre_tax_inc) and pre_tax_inc > 0:
                tax_rates.append(tax_prov / pre_tax_inc)
            elif pd.notna(tax_prov) and tax_prov == 0 and pd.notna(pre_tax_inc) and pre_tax_inc <=0 :
                 tax_rates.append(0)

        if not tax_rates:
            print(f"Warning: Could not calculate historical tax rates. Using default: {app_config.calculation.default_effective_tax_rate:.2%}.")
            effective_tax_rate = app_config.calculation.default_effective_tax_rate
        else:
            effective_tax_rate = np.mean(tax_rates)
            effective_tax_rate = max(app_config.calculation.min_effective_tax_rate, min(effective_tax_rate, app_config.calculation.max_effective_tax_rate))

        if pd.isna(effective_tax_rate): # Should be caught by previous block, but as a safeguard
            print(f"Error: Effective tax rate is NaN. Using default: {app_config.calculation.default_effective_tax_rate:.2%}.")
            effective_tax_rate = app_config.calculation.default_effective_tax_rate

        nopat = normalized_ebit * (1 - effective_tax_rate)
        print(f"NOPAT calculated: {nopat:,.0f} (Avg Tax Rate: {effective_tax_rate:.2%})")
        return nopat
    except Exception as e:
        print(f"Error calculating NOPAT: {e}")
        return None

def calculate_wacc(
    stock_details: Dict[str, Any],
    balance_sheet: pd.DataFrame,
    income_statement: pd.DataFrame,
    risk_free_rate: float,
    equity_risk_premium: Optional[float] = None,
    num_years_tax_rate: Optional[int] = None
) -> Optional[float]:
    app_config = get_config()
    if equity_risk_premium is None:
        equity_risk_premium = app_config.calculation.equity_risk_premium
    if num_years_tax_rate is None:
        num_years_tax_rate = app_config.calculation.wacc_normalization_years
    """
    Calculates the Weighted Average Cost of Capital (WACC).
    """
    try:
        beta = stock_details.get("beta")
        if beta is None or pd.isna(beta):
            print(f"Warning: Beta not available or NaN. Assuming beta = {app_config.calculation.default_beta} for WACC calculation.")
            beta = app_config.calculation.default_beta
        cost_of_equity = risk_free_rate + beta * equity_risk_premium

        market_cap = stock_details.get("market_cap")
        if market_cap is None or pd.isna(market_cap) or market_cap == 0:
            print("Error: Market Cap not available or zero. Cannot calculate WACC.")
            return None
        E = market_cap

        most_recent_year_bs = balance_sheet.iloc[:, 0]
        D = 0
        # Prioritize more comprehensive debt figures if available
        if app_config.financial_item_names.s_total_debt in most_recent_year_bs.index and pd.notna(most_recent_year_bs.loc[app_config.financial_item_names.s_total_debt]):
            D = most_recent_year_bs.loc[app_config.financial_item_names.s_total_debt]
        elif app_config.financial_item_names.s_short_long_term_debt in most_recent_year_bs.index and pd.notna(most_recent_year_bs.loc[app_config.financial_item_names.s_short_long_term_debt]):
            D = most_recent_year_bs.loc[app_config.financial_item_names.s_short_long_term_debt]
        elif app_config.financial_item_names.s_long_term_debt in most_recent_year_bs.index and pd.notna(most_recent_year_bs.loc[app_config.financial_item_names.s_long_term_debt]):
             D = most_recent_year_bs.loc[app_config.financial_item_names.s_long_term_debt]

        if D == 0:
            print("Warning: No debt found or debt is zero. WACC will equal Cost of Equity.")
            print(f"WACC calculated: {cost_of_equity:.2%} (Cost of Equity: {cost_of_equity:.2%}, No Debt)")
            return cost_of_equity

        avg_tax_rate_for_debt = app_config.calculation.default_effective_tax_rate
        if app_config.financial_item_names.s_tax_provision in income_statement.index and app_config.financial_item_names.s_pretax_income in income_statement.index:
            tax_rates_debt_list = []
            for col in income_statement.iloc[:, :num_years_tax_rate].columns:
                tax_prov = income_statement.loc[app_config.financial_item_names.s_tax_provision, col]
                pre_tax_inc = income_statement.loc[app_config.financial_item_names.s_pretax_income, col]
                if pd.notna(tax_prov) and pd.notna(pre_tax_inc) and pre_tax_inc > 0:
                    tax_rates_debt_list.append(tax_prov / pre_tax_inc)
            if tax_rates_debt_list:
                avg_tax_rate_for_debt = max(app_config.calculation.min_effective_tax_rate, min(np.mean(tax_rates_debt_list), app_config.calculation.max_effective_tax_rate))
        
        avg_interest_expense = 0
        if app_config.financial_item_names.s_interest_expense in income_statement.index:
             interest_expense_series = income_statement.loc[app_config.financial_item_names.s_interest_expense].iloc[:num_years_tax_rate]
             avg_interest_expense = abs(interest_expense_series.mean(skipna=True))


        if pd.isna(avg_interest_expense) or D == 0 or avg_interest_expense == 0 : # Added check for avg_interest_expense == 0
            print(f"Warning: Could not calculate cost of debt from financials. Using RFR + Debt Risk Premium ({app_config.calculation.debt_risk_premium:.2%}).")
            pre_tax_cost_of_debt = risk_free_rate + app_config.calculation.debt_risk_premium
        else:
            pre_tax_cost_of_debt = avg_interest_expense / D
            pre_tax_cost_of_debt = max(app_config.calculation.min_pretax_cost_of_debt, min(pre_tax_cost_of_debt, app_config.calculation.max_pretax_cost_of_debt))

        cost_of_debt_after_tax = pre_tax_cost_of_debt * (1 - avg_tax_rate_for_debt)

        V = E + D
        if V == 0:
            print("Error: Total firm value (E+D) is zero. Cannot calculate WACC.")
            return None
        wacc = (E / V) * cost_of_equity + (D / V) * cost_of_debt_after_tax

        print(f"WACC calculated: {wacc:.2%}")
        print(f"  Cost of Equity: {cost_of_equity:.2%} (Beta: {beta:.2f}, RFR: {risk_free_rate:.2%}, ERP: {equity_risk_premium:.2%})")
        print(f"  Cost of Debt (After Tax): {cost_of_debt_after_tax:.2%} (Pre-Tax: {pre_tax_cost_of_debt:.2%}, Tax Rate for Debt: {avg_tax_rate_for_debt:.2%})")
        print(f"  Market Cap (E): {E:,.0f}, Total Debt (D): {D:,.0f}")
        print(f"  Equity Weight: {E/V:.2%}, Debt Weight: {D/V:.2%}")
        return wacc
    except Exception as e:
        print(f"Error calculating WACC: {e}")
        return None

def calculate_epv(nopat: float, wacc: float, maint_capex: float) -> Optional[Dict[str, float]]:
    """
    Calculates Earnings Power Value (EPV) of Operations.
    Simplified EPV: NOPAT / WACC.
    (maint_capex is available for context or more advanced EPV adjustments if desired later)
    """
    if wacc == 0 or pd.isna(wacc): # Added NaN check for wacc
        print("Error: WACC is zero or NaN, cannot calculate EPV.")
        return None
    if pd.isna(nopat):
        print("Error: NOPAT is NaN.")
        return None

    epv_operations = nopat / wacc
    print(f"EPV (Operations) calculated: {epv_operations:,.0f}")
    return {"epv_operations": epv_operations}

def calculate_epv_equity(
    epv_operations: float,
    balance_sheet: pd.DataFrame,
    stock_details: Dict[str, Any] # Not strictly needed here now, but kept for consistency
) -> Optional[float]:
    """
    Calculates EPV of Equity from EPV of Operations.
    EPV Equity = EPV Operations + Cash & ST Investments - Total Debt - Preferred Stock BV - Noncontrolling Interest BV.
    """
    app_config = get_config()
    try:
        most_recent_bs = balance_sheet.iloc[:, 0]

        cash_and_equivalents = most_recent_bs.get(app_config.financial_item_names.s_cash_equivalents, 0)
        short_term_investments = most_recent_bs.get(app_config.financial_item_names.s_short_term_investments, 0)
        # Ensure these are numeric, default to 0 if NaN
        excess_cash_equivalents = (cash_and_equivalents if pd.notna(cash_and_equivalents) else 0) + \
                                  (short_term_investments if pd.notna(short_term_investments) else 0)

        total_debt = 0
        if app_config.financial_item_names.s_total_debt in most_recent_bs.index and pd.notna(most_recent_bs.loc[app_config.financial_item_names.s_total_debt]):
            total_debt = most_recent_bs.loc[app_config.financial_item_names.s_total_debt]
        elif app_config.financial_item_names.s_short_long_term_debt in most_recent_bs.index and pd.notna(most_recent_bs.loc[app_config.financial_item_names.s_short_long_term_debt]):
            total_debt = most_recent_bs.loc[app_config.financial_item_names.s_short_long_term_debt]
        elif app_config.financial_item_names.s_long_term_debt in most_recent_bs.index and pd.notna(most_recent_bs.loc[app_config.financial_item_names.s_long_term_debt]):
            total_debt = most_recent_bs.loc[app_config.financial_item_names.s_long_term_debt]
        
        preferred_stock_bv = most_recent_bs.get(app_config.financial_item_names.s_preferred_stock_value, 0)
        preferred_stock_bv = preferred_stock_bv if pd.notna(preferred_stock_bv) else 0

        noncontrolling_interest_bv = most_recent_bs.get(app_config.financial_item_names.s_noncontrolling_interest, 0)
        noncontrolling_interest_bv = noncontrolling_interest_bv if pd.notna(noncontrolling_interest_bv) else 0

        epv_equity = epv_operations + excess_cash_equivalents - total_debt - preferred_stock_bv - noncontrolling_interest_bv

        print(f"EPV (Equity) calculated: {epv_equity:,.0f}")
        print(f"  EPV Ops: {epv_operations:,.0f}, Excess Cash & ST Inv: {excess_cash_equivalents:,.0f}, Total Debt: {total_debt:,.0f}")
        print(f"  Preferred BV: {preferred_stock_bv:,.0f}, Noncontrolling Int BV: {noncontrolling_interest_bv:,.0f}")
        return epv_equity
    except Exception as e:
        print(f"Error calculating EPV Equity: {e}")
        return None

def calculate_asset_value_equity(balance_sheet: pd.DataFrame) -> Optional[float]:
    """
    Calculates a simplified Asset Value (Reproduction Cost) of Equity.
    Uses Net Tangible Assets or Total Stockholder Equity as a proxy.
    """
    app_config = get_config()
    if balance_sheet.empty:
        print("Error: Balance sheet is empty for Asset Value calculation.")
        return None
    try:
        most_recent_bs = balance_sheet.iloc[:, 0]
        asset_value_equity = None

        if app_config.financial_item_names.s_net_tangible_assets in most_recent_bs.index and pd.notna(most_recent_bs[app_config.financial_item_names.s_net_tangible_assets]):
            asset_value_equity = most_recent_bs[app_config.financial_item_names.s_net_tangible_assets]
            print(f"Asset Value (Equity) based on Net Tangible Assets: {asset_value_equity:,.0f}")
        elif app_config.financial_item_names.s_total_stockholder_equity in most_recent_bs.index and pd.notna(most_recent_bs[app_config.financial_item_names.s_total_stockholder_equity]):
            asset_value_equity = most_recent_bs[app_config.financial_item_names.s_total_stockholder_equity]
            print(f"Asset Value (Equity) based on Total Stockholder Equity (Book Value): {asset_value_equity:,.0f}")
        else:
            print("Warning: Could not determine Asset Value (Equity) from available balance sheet items.")
            return None
        return asset_value_equity
    except Exception as e:
        print(f"Error calculating Asset Value (Equity): {e}")
        return None

# --- Main execution block for testing this module directly ---
if __name__ == "__main__":
    print("--- Testing EPV Calculator (Refactored to use Config Manager) ---")
    try:
        # Import get_config at the top of the script if it's not already there for module use
        # from .config_manager import get_config # This should be at the top level of the script

        app_config = get_config() # Get config for the main block

        from .data_fetcher import get_ticker_object, get_historical_financials, get_stock_info, get_risk_free_rate_proxy
        from .data_processor import process_financial_data
        import sys # for the check if config was imported (no longer needed)

        sample_ticker = app_config.data_source.default_ticker 
        print(f"\nFetching and processing data for {sample_ticker} using config settings...")
        ticker_obj = get_ticker_object(sample_ticker)
        rfr = get_risk_free_rate_proxy(app_config.data_source.risk_free_rate_ticker)

        if ticker_obj and rfr is not None:
            raw_is = get_historical_financials(ticker_obj, "income_stmt")
            raw_bs = get_historical_financials(ticker_obj, "balance_sheet")
            raw_cf = get_historical_financials(ticker_obj, "cashflow")
            raw_info = get_stock_info(ticker_obj)

            if not raw_is.empty and not raw_bs.empty and not raw_cf.empty and raw_info:
                processed_data = process_financial_data(raw_is, raw_bs, raw_cf, raw_info)
                is_proc = processed_data["income_statement"]
                bs_proc = processed_data["balance_sheet"]
                cf_proc = processed_data["cash_flow"]
                details_proc = processed_data["stock_details"]

                if not is_proc.empty and not bs_proc.empty and not cf_proc.empty and details_proc:
                    print("\n--- Starting EPV Calculations (using app_config) ---")

                    # Functions will now use app_config internally for default years
                    norm_ebit_tuple = calculate_normalized_ebit(is_proc) 
                    if norm_ebit_tuple is None: raise ValueError("Normalized EBIT calculation failed.")
                    normalized_ebit, avg_op_margin = norm_ebit_tuple

                    maint_capex = calculate_maintenance_capex(is_proc, bs_proc, cf_proc)
                    if maint_capex is None:
                        print("Warning: Maintenance Capex calculation failed. Using D&A as proxy if available.")
                        if app_config.financial_item_names.s_depreciation_cf in cf_proc.index:
                             maint_capex = abs(cf_proc.loc[app_config.financial_item_names.s_depreciation_cf].iloc[:app_config.calculation.normalization_years].mean(skipna=True))
                             if pd.isna(maint_capex): raise ValueError("Maint Capex and D&A fallback failed.")
                             print(f"Using Avg D&A as Maint Capex proxy: {maint_capex:,.0f}")
                        else:
                             raise ValueError("Maint Capex failed and no D&A fallback.")

                    nopat = calculate_nopat(normalized_ebit, is_proc)
                    if nopat is None: raise ValueError("NOPAT calculation failed.")

                    # WACC will use app_config internally for defaults
                    wacc = calculate_wacc(details_proc, bs_proc, is_proc, rfr) 
                    if wacc is None: raise ValueError("WACC calculation failed.")

                    epv_results = calculate_epv(nopat, wacc, maint_capex)
                    if epv_results is None: raise ValueError("EPV Operations calculation failed.")
                    epv_ops = epv_results["epv_operations"]

                    epv_equity = calculate_epv_equity(epv_ops, bs_proc, details_proc)
                    if epv_equity is None: raise ValueError("EPV Equity calculation failed.")

                    av_equity = calculate_asset_value_equity(bs_proc)

                    print("\n--- Final Valuation Summary (from EPV Calculator Test) ---")
                    currency_symbol = app_config.output.default_currency_symbol
                    print(f"Ticker: {details_proc.get('ticker')}")
                    print(f"Current Market Price: {currency_symbol}{details_proc.get('current_price', 'N/A'):,.2f}")
                    print(f"Market Cap: {currency_symbol}{details_proc.get('market_cap', 0):,.0f}")
                    print(f"---")
                    print(f"Normalized EBIT: {currency_symbol}{normalized_ebit:,.0f} (Avg Op Margin: {avg_op_margin:.2%})")
                    print(f"Estimated Maintenance Capex: {currency_symbol}{maint_capex:,.0f}")
                    print(f"NOPAT: {currency_symbol}{nopat:,.0f}")
                    print(f"WACC: {wacc:.2%}")
                    print(f"---")
                    print(f"EPV (Operations): {currency_symbol}{epv_ops:,.0f}")
                    print(f"EPV (Equity): {currency_symbol}{epv_equity:,.0f}")
                    if av_equity is not None:
                        print(f"Asset Value (Equity Proxy): {currency_symbol}{av_equity:,.0f}")
                    print(f"---")
                    if details_proc.get('market_cap') and epv_equity:
                        mc = details_proc['market_cap']
                        mos = (epv_equity - mc) / epv_equity if epv_equity > 0 else (-1 if epv_equity <0 else 0)
                        print(f"Margin of Safety (vs EPV Equity): {mos:.2%}")
                else:
                    print("Processed data is incomplete. Cannot run EPV calculations.")
            else:
                print(f"Could not fetch complete raw data for {sample_ticker} to test EPV calculator.")
        else:
            print(f"Could not get ticker object or RFR for {sample_ticker} to test EPV calculator.")

    except ImportError as e:
        print(f"ImportError during test: {e}. Ensure all modules (config, data_fetcher, data_processor) are accessible.")
        print("If running directly, ensure config.py is in the same directory or PYTHONPATH is set.")
    except Exception as e:
        print(f"An error occurred during the EPV calculator test: {e}")
        import traceback
        traceback.print_exc()

    print("\n--- EPV Calculator Test Complete ---")


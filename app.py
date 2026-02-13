#!/usr/bin/env python3
"""
Forecast Explorer - Streamlit App
Phase 3: Interactive databook browser with charts
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
import sys

# Debug: Show Python path and available modules
if st.sidebar.checkbox("Show Debug Info", value=False):
    st.sidebar.write("Python Path:", sys.path)
    st.sidebar.write("Current Dir:", Path.cwd())

try:
    from core import get_connection
    from config import DEFAULT_RUN_ID, DEFAULT_NODE, YEARS
    from databook.builder import build_databook
except ImportError as e:
    st.error(f"Import Error: {e}")
    st.error("Make sure all files are uploaded and requirements.txt is installed.")
    st.stop()


# Page config
st.set_page_config(
    page_title="Forecast Explorer",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_data
def load_or_build_databook(run_id: str, node: str, force_rebuild: bool = False):
    """Load databook from cache or build from Athena."""
    cache_file = Path(f"cache_databook_{run_id}_{node}.csv")

    if cache_file.exists() and not force_rebuild:
        st.info(f"Loading cached databook from {cache_file}")
        return pd.read_csv(cache_file)

    st.info("Building databook from Athena... (this may take 2-3 minutes)")
    conn = get_connection()

    with st.spinner("Running Athena queries..."):
        df = build_databook(
            run_id=run_id,
            node=node,
            S=conn.S,
            q=conn.query,
            reference_csv_path="reference/scenario_databook_central.csv"
        )

    conn.close()

    # Cache to file
    df.to_csv(cache_file, index=False)
    st.success(f"Databook built and cached to {cache_file}")

    return df


def load_reference():
    """Load reference databook for comparison."""
    return pd.read_csv("reference/scenario_databook_central.csv")


def get_color_for_diff(pct_diff):
    """Return color based on percentage difference."""
    if pct_diff is None or pd.isna(pct_diff):
        return ""
    if pct_diff < 1:
        return "background-color: #d4edda"  # green
    elif pct_diff < 5:
        return "background-color: #fff3cd"  # yellow
    else:
        return "background-color: #f8d7da"  # red


def main():
    st.title("⚡ Forecast Explorer")
    st.markdown("---")

    # Sidebar
    with st.sidebar:
        st.header("Configuration")

        run_id = st.selectbox(
            "Run ID",
            [DEFAULT_RUN_ID],
            help="Forecast scenario run ID"
        )

        node = st.selectbox(
            "Node/Region",
            [DEFAULT_NODE],
            help="Geographic region"
        )

        force_rebuild = st.checkbox(
            "Force rebuild from Athena",
            help="Clear cache and rebuild from database"
        )

        st.markdown("---")
        st.markdown("### About")
        st.markdown("""
        **Forecast Explorer** generates annual scenario databooks from Athena forecast data.

        - 📊 **Databook**: Full 118-row table
        - 📈 **Charts**: Key visualizations
        - 🔍 **Drill Down**: Time series analysis
        """)

    # Load data
    computed_df = load_or_build_databook(run_id, node, force_rebuild)
    reference_df = load_reference()

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 Databook", "📈 Charts", "🔍 Drill Down"])

    # TAB 1: Databook
    with tab1:
        st.header("Complete Databook")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Rows", len(computed_df))
        with col2:
            st.metric("Years", f"{YEARS[0]}-{YEARS[-1]}")
        with col3:
            st.metric("Columns", len(computed_df.columns))

        st.markdown("---")

        # Filter by variable type
        var_types = ["All"] + sorted(computed_df['Variable Type'].unique().tolist())
        selected_type = st.selectbox("Filter by Variable Type", var_types)

        if selected_type != "All":
            display_df = computed_df[computed_df['Variable Type'] == selected_type].copy()
        else:
            display_df = computed_df.copy()

        # Show dataframe
        st.dataframe(
            display_df,
            use_container_width=True,
            height=600
        )

        # Download button
        csv = display_df.to_csv(index=False)
        st.download_button(
            label="📥 Download as CSV",
            data=csv,
            file_name=f"databook_{run_id}_{node}.csv",
            mime="text/csv"
        )

    # TAB 2: Charts
    with tab2:
        st.header("Key Visualizations")

        chart_type = st.selectbox(
            "Select Chart",
            [
                "Price Trajectory",
                "Generation Mix",
                "Storage Buildout",
                "Spread Evolution",
                "Demand Growth",
                "Capture Rates"
            ]
        )

        st.markdown("---")

        if chart_type == "Price Trajectory":
            # Average wholesale price over time
            price_row = computed_df[
                (computed_df['Variable Type'] == 'Wholesale Power Prices') &
                (computed_df['Variable'] == 'Average') &
                (computed_df['Currency'] == 'Global')
            ]

            if not price_row.empty:
                year_cols = [str(y) for y in YEARS]
                prices = []
                for yr in year_cols:
                    if yr in price_row.columns:
                        val = price_row.iloc[0][yr]
                        if pd.notna(val):
                            prices.append({'Year': int(yr), 'Price': val})

                df_plot = pd.DataFrame(prices)

                fig = px.line(
                    df_plot,
                    x='Year',
                    y='Price',
                    title='Average Wholesale Power Price (EUR_2025/MWh)',
                    markers=True
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

                st.markdown(f"""
                **Key Insights:**
                - 2026 average: €{df_plot[df_plot['Year']==2026]['Price'].iloc[0]:.2f}/MWh
                - 2040 average: €{df_plot[df_plot['Year']==2040]['Price'].iloc[0]:.2f}/MWh
                - 2059 average: €{df_plot[df_plot['Year']==2059]['Price'].iloc[0]:.2f}/MWh
                """)

        elif chart_type == "Generation Mix":
            # Stacked area of generation output
            gen_types = ['Solar', 'Onshore Wind', 'Offshore Wind', 'Gas CCGT', 'CCS Gas CCGT', 'H2 Peaker']
            gen_data = []

            for tech in gen_types:
                tech_row = computed_df[
                    (computed_df['Variable Type'] == 'Generation Out-turn') &
                    (computed_df['Variable'] == tech)
                ]

                if not tech_row.empty:
                    for yr in [str(y) for y in YEARS]:
                        if yr in tech_row.columns:
                            val = tech_row.iloc[0][yr]
                            if pd.notna(val):
                                gen_data.append({
                                    'Year': int(yr),
                                    'Technology': tech,
                                    'Generation (TWh)': val
                                })

            if gen_data:
                df_plot = pd.DataFrame(gen_data)

                fig = px.area(
                    df_plot,
                    x='Year',
                    y='Generation (TWh)',
                    color='Technology',
                    title='Generation Mix Evolution (TWh)'
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "Storage Buildout":
            # Storage capacity by duration
            storage_types = [
                'Battery Storage 1h (Grid)',
                'Battery Storage 2h (Grid)',
                'Battery Storage 4h (Grid)',
                'Battery Storage 6h (Grid)',
                'Battery Storage 8h (Grid)'
            ]

            storage_data = []
            for stype in storage_types:
                stype_row = computed_df[
                    (computed_df['Variable Type'] == 'Storage Power Capacity') &
                    (computed_df['Variable'] == stype)
                ]

                if not stype_row.empty:
                    for yr in [str(y) for y in YEARS]:
                        if yr in stype_row.columns:
                            val = stype_row.iloc[0][yr]
                            if pd.notna(val):
                                storage_data.append({
                                    'Year': int(yr),
                                    'Duration': stype,
                                    'Capacity (GW)': val
                                })

            if storage_data:
                df_plot = pd.DataFrame(storage_data)

                fig = px.line(
                    df_plot,
                    x='Year',
                    y='Capacity (GW)',
                    color='Duration',
                    title='Battery Storage Buildout by Duration (GW)',
                    markers=True
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "Spread Evolution":
            # TB1, TB2, TB4 spreads over time
            spread_data = []
            for spread in ['TB1', 'TB2', 'TB4']:
                spread_row = computed_df[
                    (computed_df['Variable Type'] == 'Wholesale Power Price Spreads') &
                    (computed_df['Variable'] == spread) &
                    (computed_df['Currency'] == 'Global')
                ]

                if not spread_row.empty:
                    for yr in [str(y) for y in YEARS]:
                        if yr in spread_row.columns:
                            val = spread_row.iloc[0][yr]
                            if pd.notna(val):
                                spread_data.append({
                                    'Year': int(yr),
                                    'Spread': spread,
                                    'Value (EUR/MW/yr)': val
                                })

            if spread_data:
                df_plot = pd.DataFrame(spread_data)

                fig = px.line(
                    df_plot,
                    x='Year',
                    y='Value (EUR/MW/yr)',
                    color='Spread',
                    title='Price Spreads Evolution (EUR_2025/MW/yr)',
                    markers=True
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "Demand Growth":
            # Annual demand trajectory
            demand_row = computed_df[
                (computed_df['Variable Type'] == 'Demand') &
                (computed_df['Variable'] == 'Annual')
            ]

            if not demand_row.empty:
                demand_data = []
                for yr in [str(y) for y in YEARS]:
                    if yr in demand_row.columns:
                        val = demand_row.iloc[0][yr]
                        if pd.notna(val):
                            demand_data.append({'Year': int(yr), 'Demand (TWh)': val})

                df_plot = pd.DataFrame(demand_data)

                fig = px.line(
                    df_plot,
                    x='Year',
                    y='Demand (TWh)',
                    title='Annual Electricity Demand (TWh)',
                    markers=True
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

                # CAGR calculation
                start_val = df_plot[df_plot['Year']==2026]['Demand (TWh)'].iloc[0]
                end_val = df_plot[df_plot['Year']==2059]['Demand (TWh)'].iloc[0]
                years = 2059 - 2026
                cagr = ((end_val / start_val) ** (1/years) - 1) * 100

                st.markdown(f"""
                **Growth Metrics:**
                - 2026: {start_val:.1f} TWh
                - 2059: {end_val:.1f} TWh
                - Total growth: {((end_val - start_val) / start_val * 100):.1f}%
                - CAGR: {cagr:.2f}%/year
                """)

        elif chart_type == "Capture Rates":
            # Capture rates for renewables
            capture_data = []
            for tech in ['Solar', 'Onshore Wind', 'Offshore Wind']:
                tech_row = computed_df[
                    (computed_df['Variable Type'] == 'Capture Rate') &
                    (computed_df['Variable'] == tech)
                ]

                if not tech_row.empty:
                    for yr in [str(y) for y in YEARS]:
                        if yr in tech_row.columns:
                            val = tech_row.iloc[0][yr]
                            if pd.notna(val):
                                capture_data.append({
                                    'Year': int(yr),
                                    'Technology': tech,
                                    'Capture Rate (%)': val
                                })

            if capture_data:
                df_plot = pd.DataFrame(capture_data)

                fig = px.line(
                    df_plot,
                    x='Year',
                    y='Capture Rate (%)',
                    color='Technology',
                    title='Renewable Capture Rates (%)',
                    markers=True
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

                st.markdown("""
                **What is Capture Rate?**

                Capture rate measures how much revenue a renewable generator earns compared to the average market price.
                A 50% capture rate means the generator earns half the average price (because it generates when prices are low).

                As renewable penetration increases, capture rates decline due to cannibalization.
                """)

    # TAB 3: Drill Down
    with tab3:
        st.header("Time Series Drill Down")

        st.markdown("Select any metric to see its trajectory over time:")

        col1, col2 = st.columns(2)

        with col1:
            var_type = st.selectbox(
                "Variable Type",
                sorted(computed_df['Variable Type'].unique())
            )

        # Filter variables by type
        vars_for_type = computed_df[computed_df['Variable Type'] == var_type]['Variable'].unique()

        with col2:
            variable = st.selectbox(
                "Variable",
                sorted(vars_for_type)
            )

        # Get matching rows
        matching = computed_df[
            (computed_df['Variable Type'] == var_type) &
            (computed_df['Variable'] == variable)
        ]

        if len(matching) > 1:
            # Multiple rows (e.g., Global vs Local)
            st.info(f"Found {len(matching)} rows for this metric (e.g., Global/Local)")

            for idx, row in matching.iterrows():
                currency = row.get('Currency', '')
                title_suffix = f" ({currency})" if currency else ""

                # Extract time series
                ts_data = []
                for yr in [str(y) for y in YEARS]:
                    if yr in row.index:
                        val = row[yr]
                        if pd.notna(val):
                            ts_data.append({'Year': int(yr), 'Value': val})

                if ts_data:
                    df_plot = pd.DataFrame(ts_data)

                    fig = px.line(
                        df_plot,
                        x='Year',
                        y='Value',
                        title=f"{var_type}: {variable}{title_suffix}",
                        markers=True
                    )
                    fig.update_layout(height=400)
                    st.plotly_chart(fig, use_container_width=True)

        elif len(matching) == 1:
            row = matching.iloc[0]

            # Extract time series
            ts_data = []
            for yr in [str(y) for y in YEARS]:
                if yr in row.index:
                    val = row[yr]
                    if pd.notna(val):
                        ts_data.append({'Year': int(yr), 'Value': val})

            if ts_data:
                df_plot = pd.DataFrame(ts_data)

                units = row.get('Units', '')

                fig = px.line(
                    df_plot,
                    x='Year',
                    y='Value',
                    title=f"{var_type}: {variable} ({units})",
                    markers=True
                )
                fig.update_layout(height=500)
                st.plotly_chart(fig, use_container_width=True)

                # Show statistics
                st.markdown("### Statistics")
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.metric("Min", f"{df_plot['Value'].min():.2f}")
                with col2:
                    st.metric("Max", f"{df_plot['Value'].max():.2f}")
                with col3:
                    st.metric("Mean", f"{df_plot['Value'].mean():.2f}")
                with col4:
                    st.metric("2026 Value", f"{df_plot[df_plot['Year']==2026]['Value'].iloc[0]:.2f}")


if __name__ == "__main__":
    main()

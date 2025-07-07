# Import necessary libraries
import os
import base64
import io
from io import StringIO # Explicitly import StringIO
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import dash
from dash import Dash, dcc, html, Input, Output, State, dash_table, callback_context
import dash_bootstrap_components as dbc # Added for better styling of buttons/inputs

# Initialize the Dash app
# Add external stylesheets for Tailwind CSS and Dash Bootstrap Components
app = Dash(__name__, external_stylesheets=[
    'https://unpkg.com/tailwindcss@^2/dist/tailwind.min.css',
    dbc.themes.BOOTSTRAP # For dbc components like Switch and Button
])

# Helper function to parse uploaded content (moved outside callback for clarity)
def parse_contents(contents, filename):
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    try:
        if 'xls' in filename or 'xlsx' in filename:
            df = pd.read_excel(io.BytesIO(decoded))
        else:
            return html.Div([
                html.P("Please upload an Excel file (.xlsx or .xls).", className="text-red-500 text-center")
            ])
    except Exception as e:
        print(f"Error parsing file {filename}: {e}")
        return html.Div([
            html.P(f"There was an error processing file '{filename}': {e}", className="text-red-500 text-center")
        ])

    # --- Data Cleaning and Preprocessing (NWR Billing Specific) ---
    df.columns = df.columns.str.strip().str.replace(' ', '_').str.lower()

    date_col = None
    for col in ['date', 'invoice_date', 'billing_date', 'transaction_date']:
        if col in df.columns:
            date_col = col
            break

    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df = df.dropna(subset=[date_col])
        df = df.sort_values(by=date_col)
    else:
        return html.Div([
            html.P("Could not find a suitable date column (e.g., 'date', 'invoice date'). Please ensure your file has one.", className="text-red-500 text-center")
        ])

    amount_col = None
    for col in ['amount', 'amount_billed', 'total_amount', 'price']:
        if col in df.columns:
            amount_col = col
            break

    if amount_col:
        df[amount_col] = pd.to_numeric(df[amount_col], errors='coerce')
        df = df.dropna(subset=[amount_col])
    else:
        return html.Div([
            html.P("Could not find a suitable amount column (e.g., 'amount', 'amount billed'). Please ensure your file has one.", className="text-red-500 text-center")
        ])

    # Convert DataFrame to JSON string. 'orient='records'' is suitable for dcc.Store.
    return df.to_json(date_format='iso', orient='records')

# Define the layout of the app
app.layout = html.Div(
    id='main-app-container',
    style={'fontFamily': '"Trebuchet MS", "Lucida Grande", "Lucida Sans Unicode", "Lucida Sans", Tahoma, sans-serif'},
    className="min-h-screen bg-gray-100 p-8 transition-colors duration-300", # Default light theme for overall background
    children=[
        # Header section (fixed styling)
        html.Div(
            className="bg-white p-6 rounded-xl shadow-xl mb-8 text-center",
            children=[
                html.H1(
                    "NWR Billing Data Analytics Dashboard",
                    className="text-3xl md:text-4xl font-bold text-[#004369] mb-2" # Dark Blue from palette
                ),
                html.P(
                    "Upload your Excel file to analyze billing data and visualize key metrics.",
                    className="text-gray-600"
                )
            ]
        ),

        # File upload component and new controls (fixed styling)
        html.Div(
            className="bg-white p-6 rounded-xl shadow-xl mb-8 flex flex-col items-center",
            children=[
                dcc.Upload(
                    id='upload-data',
                    children=html.Div(
                        className="w-full p-6 border-2 border-dashed border-blue-300 rounded-xl text-center cursor-pointer hover:bg-blue-50 transition-colors duration-200",
                        children=[
                            html.P("Drag and Drop or Click to Select Excel File", className="text-blue-600 text-lg font-semibold"),
                            html.P("(.xlsx, .xls)", className="text-gray-500 text-sm")
                        ]
                    ),
                    multiple=False,
                    className="mb-6 w-full" # Increased mb for better spacing
                ),
                html.Div(
                    className="flex flex-col md:flex-row items-center justify-center md:space-x-8 space-y-4 md:space-y-0 w-full", # Improved spacing and responsiveness
                    children=[
                        dbc.Button(
                            "Clear All Data",
                            id='clear-data-button',
                            n_clicks=0,
                            color="danger", # Red button for danger (clear)
                            className="w-full md:w-auto px-6 py-3 rounded-lg shadow-md hover:shadow-lg transition-all duration-200" # Enhanced button styling
                        ),
                        html.Div( # Wrapper for checklist to control its spacing
                            className="flex items-center space-x-2 text-gray-700 font-medium", # Added space-x for checkbox and label
                            children=[
                                dcc.Checklist(
                                    id='merge-data-checkbox',
                                    options=[{'label': '', 'value': 'append'}], # Empty label, text is next to it
                                    value=[],
                                    inline=True,
                                    className="p-0 m-0" # Remove default padding/margin from checklist
                                ),
                                html.Label("Append new data to existing", htmlFor='merge-data-checkbox', className="cursor-pointer") # Explicit label for better accessibility and alignment
                            ]
                        ),
                    ]
                )
            ]
        ),

        # Loading indicator for data processing
        dcc.Loading(
            id="loading-output",
            type="circle",
            children=html.Div(id='output-dashboard-container')
        ),

        # Hidden div to store parsed data (JSON string)
        dcc.Store(id='stored-data', storage_type='memory'),
    ]
)

# Combined Callback to handle file upload, data clearing, and dashboard rendering
@app.callback(
    Output('stored-data', 'data'),
    Output('output-dashboard-container', 'children'),
    Input('upload-data', 'contents'),
    Input('clear-data-button', 'n_clicks'),
    State('upload-data', 'filename'),
    State('stored-data', 'data'),
    State('merge-data-checkbox', 'value'),
    prevent_initial_call=True
)
def update_and_display_dashboard(uploaded_contents, clear_clicks, uploaded_filename, current_data_json, merge_option):
    ctx = callback_context

    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # Define fixed light mode colors for charts and tables
    plot_bg = 'white'
    paper_bg = 'white'
    font_color = '#333'
    card_bg = 'white'
    header_bg = 'rgb(230, 230, 230)'
    table_text_color = 'black'
    dynamic_heading_color = '#004369' # Dark Blue from palette for dynamic content
    dynamic_sub_heading_color = '#01949A' # Teal from palette for dynamic content
    axis_line_color = '#E5E7EB' # gray-200 for axis lines
    grid_line_color = '#F3F4F6' # gray-100 for grid lines

    # Define chart accent colors (fixed for light mode)
    chart_accent_colors = {
        'primary': '#01949A', # Teal
        'secondary': '#004369', # Dark Blue
        'tertiary': '#DB1F48', # Red
        'quaternary': '#87CEEB', # Light Blue
        'neutral': '#A9A9A9' # Gray
    }


    # CASE 1: Clear Data Button is clicked
    if trigger_id == 'clear-data-button' and clear_clicks > 0:
        return None, html.Div([
            html.P("Data cleared! Please upload new data.", className="text-blue-600 text-center mt-8")
        ], className=f"bg-{card_bg} p-6 rounded-xl shadow-xl transition-colors duration-300 text-{font_color}")


    # CASE 2: File is uploaded
    final_df = pd.DataFrame() # Initialize empty DataFrame
    display_message = ""

    if trigger_id == 'upload-data' and uploaded_contents is not None:
        parsed_json_or_error_div = parse_contents(uploaded_contents, uploaded_filename)

        if isinstance(parsed_json_or_error_div, html.Div):
            # If parse_contents returned an error, keep existing data if any, and show error
            return current_data_json, html.Div([
                parsed_json_or_error_div
            ], className=f"bg-{card_bg} p-6 rounded-xl shadow-xl transition-colors duration-300 text-{font_color}")
        
        new_df = pd.read_json(StringIO(parsed_json_or_error_div), orient='records') # Wrapped with StringIO

        if 'append' in merge_option and current_data_json:
            try:
                existing_df = pd.read_json(StringIO(current_data_json), orient='records') # Wrapped with StringIO
                # Ensure date columns are datetime objects before concatenation for consistent types
                date_col_existing = None
                for col in ['date', 'invoice_date', 'billing_date', 'transaction_date']:
                    if col in existing_df.columns:
                        date_col_existing = col
                        break
                if date_col_existing:
                    existing_df[date_col_existing] = pd.to_datetime(existing_df[date_col_existing], errors='coerce')

                date_col_new = None
                for col in ['date', 'invoice_date', 'billing_date', 'transaction_date']:
                    if col in new_df.columns:
                        date_col_new = col
                        break
                if date_col_new:
                    new_df[date_col_new] = pd.to_datetime(new_df[date_col_new], errors='coerce')

                common_cols = list(set(existing_df.columns) & set(new_df.columns))
                final_df = pd.concat([existing_df[common_cols], new_df[common_cols]], ignore_index=True)
                final_df = final_df.drop_duplicates().reset_index(drop=True)
                display_message = f"File '{uploaded_filename}' appended successfully! Total unique rows: {len(final_df)}."
            except Exception as e:
                print(f"Error appending data: {e}")
                return current_data_json, html.Div([
                    html.P(f"Error appending data: {e}. Displaying original data.", className="text-red-500 text-center")
                ], className=f"bg-{card_bg} p-6 rounded-xl shadow-xl transition-colors duration-300 text-{font_color}")
        else:
            final_df = new_df
            display_message = f"File '{uploaded_filename}' processed successfully! Total rows: {len(final_df)}."
    
    elif not current_data_json:
        # No data uploaded yet, or data was cleared
        return None, html.Div([
            html.P("Upload an Excel file to see the dashboard.", className="text-gray-500 text-center mt-8")
        ], className=f"bg-{card_bg} p-6 rounded-xl shadow-xl transition-colors duration-300 text-{font_color}")
    else:
        # This case handles initial load with prevent_initial_call=True
        # or if current_data_json exists but no other trigger.
        final_df = pd.read_json(StringIO(current_data_json), orient='records') # Wrapped with StringIO
        display_message = "Dashboard ready."


    # Re-convert date column after reading from JSON (if it became string)
    date_col = None
    for col in ['date', 'invoice_date', 'billing_date', 'transaction_date']:
        if col in final_df.columns:
            date_col = col
            break
    if date_col:
        final_df[date_col] = pd.to_datetime(final_df[date_col], errors='coerce')
        final_df = final_df.dropna(subset=[date_col])
        final_df = final_df.sort_values(by=date_col)

    # Infer amount and customer/service columns again
    amount_col = None
    for col in ['amount', 'amount_billed', 'total_amount', 'price']:
        if col in final_df.columns:
            amount_col = col
            break
    
    customer_col = None
    for col in ['customer', 'customer_name', 'client']:
        if col in final_df.columns:
            customer_col = col
            break

    service_col = None
    for col in ['service_type', 'service', 'product']:
        if col in final_df.columns:
            service_col = col
            break

    # If essential columns are missing or final_df is empty, return an error message
    if final_df.empty or not all([date_col, amount_col]):
        return final_df.to_json(date_format='iso', orient='records'), html.Div([
            html.P("No valid data found after processing, or essential columns (date, amount) are missing. Please check your Excel file.", className="text-red-500 text-center")
        ], className=f"bg-{card_bg} p-6 rounded-xl shadow-xl transition-colors duration-300 text-{font_color}")

    # --- Dashboard Visualizations ---

    # 1. Total Billing Amount Over Time (Line Chart)
    final_df['year_month'] = final_df[date_col].dt.to_period('M').astype(str)
    time_series_data = final_df.groupby('year_month')[amount_col].sum().reset_index()
    
    fig_time_series = go.Figure() # Initialize an empty figure
    if not time_series_data.empty:
        fig_time_series = px.line(
            time_series_data,
            x='year_month',
            y=amount_col,
            title='Total Billing Amount Over Time',
            labels={'year_month': 'Month', amount_col: 'Total Amount'},
            markers=True
        )
    else:
        fig_time_series.add_annotation(text="No data for billing trends.", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=16, color=font_color))
    fig_time_series.update_layout(
        plot_bgcolor=plot_bg,
        paper_bgcolor=paper_bg,
        font_color=font_color,
        margin=dict(l=40, r=40, t=40, b=40),
        xaxis=dict(gridcolor=grid_line_color, linecolor=axis_line_color, tickfont=dict(color=font_color)), # Dynamic axis colors
        yaxis=dict(gridcolor=grid_line_color, linecolor=axis_line_color, tickfont=dict(color=font_color))  # Dynamic axis colors
    )


    # 2. Billing Amount by Service Type (Bar Chart)
    fig_service_type = go.Figure() # Initialize an empty figure
    if service_col and service_col in final_df.columns and not final_df[service_col].empty:
        service_type_data = final_df.groupby(service_col)[amount_col].sum().reset_index().sort_values(by=amount_col, ascending=False)
        if not service_type_data.empty:
            fig_service_type = px.bar(
                service_type_data,
                x=service_col,
                y=amount_col,
                title='Billing Amount by Service Type',
                labels={service_col: 'Service Type', amount_col: 'Total Amount'},
                color=service_col,
                color_discrete_sequence=[chart_accent_colors['primary'], chart_accent_colors['secondary'], chart_accent_colors['tertiary'], chart_accent_colors['neutral']]
            )
        else:
            fig_service_type.add_annotation(text="No data for service type breakdown.", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=16, color=font_color))
    else:
        fig_service_type.add_annotation(text="Service type column not found or no data.", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=16, color=font_color))
    fig_service_type.update_layout(
        plot_bgcolor=plot_bg,
        paper_bgcolor=paper_bg,
        font_color=font_color,
        margin=dict(l=40, r=40, t=40, b=40),
        xaxis=dict(gridcolor=grid_line_color, linecolor=axis_line_color, tickfont=dict(color=font_color)), # Dynamic axis colors
        yaxis=dict(gridcolor=grid_line_color, linecolor=axis_line_color, tickfont=dict(color=font_color))  # Dynamic axis colors
    )


    # 3. Top 10 Customers by Billing Amount (Bar Chart)
    fig_top_customers = go.Figure() # Initialize an empty figure
    if customer_col and customer_col in final_df.columns and not final_df[customer_col].empty:
        customer_data = final_df.groupby(customer_col)[amount_col].sum().reset_index().sort_values(by=amount_col, ascending=False).head(10)
        if not customer_data.empty:
            fig_top_customers = px.bar(
                customer_data,
                x=customer_col,
                y=amount_col,
                title='Top 10 Customers by Billing Amount',
                labels={customer_col: 'Customer', amount_col: 'Total Amount'},
                color=customer_col,
                color_discrete_sequence=[chart_accent_colors['primary'], chart_accent_colors['secondary'], chart_accent_colors['tertiary'], chart_accent_colors['quaternary'], chart_accent_colors['neutral']]
            )
        else:
            fig_top_customers.add_annotation(text="No data for top customers.", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=16, color=font_color))
    else:
        fig_top_customers.add_annotation(text="Customer column not found or no data.", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False, font=dict(size=16, color=font_color))
    fig_top_customers.update_layout(
        plot_bgcolor=plot_bg,
        paper_bgcolor=paper_bg,
        font_color=font_color,
        margin=dict(l=40, r=40, t=40, b=40),
        xaxis=dict(gridcolor=grid_line_color, linecolor=axis_line_color, tickfont=dict(color=font_color)), # Dynamic axis colors
        yaxis=dict(gridcolor=grid_line_color, linecolor=axis_line_color, tickfont=dict(color=font_color))  # Dynamic axis colors
    )


    # 4. Summary Statistics Table
    summary_stats_columns = [{"name": "Statistic", "id": "Statistic"}, {"name": "Value", "id": "Value"}]
    summary_stats_data = []
    if not final_df.empty and amount_col and not final_df[[amount_col]].empty:
        try:
            summary_stats = final_df[[amount_col]].describe().reset_index()
            summary_stats.columns = ['Statistic', 'Value']
            summary_stats['Value'] = summary_stats['Value'].apply(lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x)
            summary_stats_data = summary_stats.to_dict('records')
        except Exception as e:
            print(f"Error generating summary statistics: {e}")
            summary_stats_data = [{'Statistic': 'Error', 'Value': 'N/A'}]
    else:
        summary_stats_data = [{'Statistic': 'No Data', 'Value': 'N/A'}]


    # Raw Data Preview Table
    raw_data_columns = []
    raw_data_records = []
    if not final_df.empty:
        raw_data_columns = [{"name": i, "id": i} for i in final_df.columns]
        raw_data_records = final_df.to_dict('records')
    else:
        raw_data_columns = [{"name": "No Data", "id": "No Data"}]
        raw_data_records = [{'No Data': 'Upload an Excel file to see raw data.'}]


    # Dashboard content structure
    dashboard_content = html.Div(
        className="grid grid-cols-1 lg:grid-cols-2 gap-8",
        children=[
            html.Div(
                className=f"bg-{card_bg} p-6 rounded-xl shadow-xl max-h-96 overflow-y-auto transition-colors duration-300 text-{font_color}",
                children=[
                    html.H3("Billing Trends", className=f"text-xl font-semibold text-{dynamic_heading_color} mb-4 text-center"),
                    dcc.Graph(figure=fig_time_series)
                ]
            ),
            html.Div(
                className=f"bg-{card_bg} p-6 rounded-xl shadow-xl max-h-96 overflow-y-auto transition-colors duration-300 text-{font_color}",
                children=[
                    html.H3("Summary Statistics", className=f"text-xl font-semibold text-{dynamic_heading_color} mb-4 text-center"),
                    dash_table.DataTable(
                        id='summary-table',
                        columns=summary_stats_columns,
                        data=summary_stats_data,
                        style_table={'overflowX': 'auto', 'height': '100%'}, # Ensure table itself scrolls
                        style_header={
                            'backgroundColor': header_bg,
                            'fontWeight': 'bold',
                            'textAlign': 'left',
                            'color': table_text_color
                        },
                        style_data={
                            'backgroundColor': card_bg,
                            'color': table_text_color,
                            'textAlign': 'left'
                        },
                        style_cell={'padding': '8px', 'minWidth': '100px', 'width': '100px', 'maxWidth': '180px', 'whiteSpace': 'normal'}
                    )
                ]
            ),
            html.Div(
                className=f"bg-{card_bg} p-6 rounded-xl shadow-xl max-h-96 overflow-y-auto transition-colors duration-300 text-{font_color}",
                children=[
                    html.H3("Billing by Service Type", className=f"text-xl font-semibold text-{dynamic_heading_color} mb-4 text-center"),
                    dcc.Graph(figure=fig_service_type)
                ]
            ),
            html.Div(
                className=f"bg-{card_bg} p-6 rounded-xl shadow-xl max-h-96 overflow-y-auto transition-colors duration-300 text-{font_color}",
                children=[
                    html.H3("Top Customers", className=f"text-xl font-semibold text-{dynamic_heading_color} mb-4 text-center"),
                    dcc.Graph(figure=fig_top_customers)
                ]
            ),
            html.Div(
                className=f"bg-{card_bg} p-6 rounded-xl shadow-xl lg:col-span-2 max-h-96 overflow-y-auto transition-colors duration-300 text-{font_color}",
                children=[
                    html.H3("Raw Data Preview", className=f"text-xl font-semibold text-{dynamic_heading_color} mb-4 text-center"),
                    dash_table.DataTable(
                        id='data-table',
                        columns=raw_data_columns,
                        data=raw_data_records,
                        page_size=10,
                        sort_action="native",
                        filter_action="native",
                        style_table={'overflowX': 'auto', 'height': '100%'}, # Ensure table itself scrolls
                        style_header={
                            'backgroundColor': header_bg,
                            'fontWeight': 'bold',
                            'textAlign': 'left',
                            'color': table_text_color
                        },
                        style_data={
                            'backgroundColor': card_bg,
                            'color': table_text_color,
                            'textAlign': 'left'
                        },
                        style_cell={'padding': '8px', 'minWidth': '100px', 'width': '100px', 'maxWidth': '180px', 'whiteSpace': 'normal'}
                    )
                ]
            )
        ]
    )
    
    # Return the processed data (as JSON) and the dashboard layout
    return final_df.to_json(date_format='iso', orient='records'), html.Div([
        html.P(display_message, className=f"text-green-600 text-center mt-4 mb-4 text-{font_color}"),
        dashboard_content
    ], className=f"bg-{card_bg} p-6 rounded-xl shadow-xl transition-colors duration-300")


# Run the app
if __name__ == '__main__':
    # Get port from environment variable, default to 8050 if not set
    # This is crucial for deployment platforms like Streamlit Cloud, Heroku, Render, etc.
    # They assign a dynamic port.
    port = os.environ.get('PORT', 8050)

    # Get host from environment variable, default to '0.0.0.0' for external access
    # '0.0.0.0' makes the app accessible from outside the container/server
    host = os.environ.get('HOST', '0.0.0.0')

    app.run(host=host, port=port) # debug=True has been removed

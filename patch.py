import glob
import re
import os

# 1. Update dashboard_data.py to accept graph_type
dd_path = "dashboard/dashboard_data.py"
with open(dd_path, "r", encoding="utf-8") as f:
    dd_content = f.read()

new_theme_func = """def apply_premium_theme(fig, graph_type="line"):
    \"\"\"Applies modern dark-mode formatting to Plotly figures.\"\"\"
    
    # 1. Füge sichtbare Punkte ("markers") und die echten Zahlenwerte ("text") hinzu
    if graph_type == "line":
        fig.update_traces(
            mode="lines+markers+text",
            texttemplate="%{y:.0f}",
            textposition="top center",
            marker=dict(size=8),
            selector=dict(type="scatter", mode="lines") # Only target lines
        )
        # Ensure we also hit default px.line which may lack explicit mode
        for trace in fig.data:
            if trace.type == 'scatter' and (trace.mode == 'lines' or trace.mode is None):
                trace.mode = 'lines+markers+text'
                trace.texttemplate = '%{y:.0f}'
                trace.textposition = 'top center'
                trace.marker.size = 8
    
    elif graph_type == "bar":
        fig.update_traces(
            texttemplate="%{y:.0f}",
            textposition="outside",
            selector=dict(type="bar")
        )
    elif graph_type == "scatter":
        fig.update_traces(
            mode="markers+text",
            texttemplate="%{y:.0f}",
            textposition="top center",
            marker=dict(size=8),
            selector=dict(type="scatter")
        )

    # 2. Übriges Design (Dark-Mode, Fonts...)
    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=50, l=10, r=10, b=10),
        font=dict(family="sans serif", size=12, color="#E2E8F0"),
        hoverlabel=dict(
            bgcolor="#1E293B",
            font_size=13,
            font_family="sans serif"
        )
    )
    # Refine grid visibility for sleeker look
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor="rgba(255,255,255,0.05)")
    return fig"""

# Replace the old apply_premium_theme with the new one
old_theme_start = dd_content.find("def apply_premium_theme(fig):")
if old_theme_start != -1:
    dd_content = dd_content[:old_theme_start] + new_theme_func + "\n"
    with open(dd_path, "w", encoding="utf-8") as f:
        f.write(dd_content)

# 2. Patch all pages
pages = glob.glob("dashboard/pages/*.py")

def patch_page(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Add imports
    if "inject_custom_css" not in content:
        content = re.sub(
            r'from dashboard_data import(.*)', 
            r'from dashboard_data import\1, inject_custom_css, apply_premium_theme', 
            content
        )
    
    # Add inject_custom_css
    if "inject_custom_css()" not in content:
        content = re.sub(
            r'(st\.set_page_config[^\n]+)\n',
            r'\1\ninject_custom_css()\n',
            content
        )

    # Convert px.* to specify graph_type in apply_premium_theme wrapping
    # Instead of wrapping in st.plotly_chart, let's inject a line BEFORE st.plotly_chart.
    # We look for lines matching: `fig... = px.something(...)`
    # and we want to ensure `fig... = apply_premium_theme(fig..., graph_type="...")` is after it.

    lines = content.split('\n')
    new_lines = []
    for line in lines:
        new_lines.append(line)
        match = re.search(r'^(\s*)(\w+)\s*=\s*px\.(line|bar|scatter|pie|imshow)\(', line)
        if match:
            indent = match.group(1)
            var_name = match.group(2)
            g_type = match.group(3)
            # pie and imshow don't need text markers, but we can apply the base theme
            if g_type in ("pie", "imshow"):
                g_type = "other"
            new_lines.append(f'{indent}{var_name} = apply_premium_theme({var_name}, graph_type="{g_type}")')

    new_content = "\n".join(new_lines)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)

for p in pages:
    patch_page(p)

print("Done patching.")

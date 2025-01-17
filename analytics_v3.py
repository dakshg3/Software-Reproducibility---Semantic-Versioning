import pandas as pd
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import AgglomerativeClustering
from collections import Counter
import re
import math

csv_file = 'data.csv'

def load_and_clean_data(csv_file):
    """Loads and cleans the dataset."""
    try:
        df = pd.read_csv(csv_file, skipinitialspace=True)
    except FileNotFoundError:
        print(f"Error: File '{csv_file}' not found.")
        return pd.DataFrame()
    except pd.errors.EmptyDataError:
        print("Error: No data found in the CSV file.")
        return pd.DataFrame()
    except Exception as e:
        print(f"An unexpected error occurred while reading the CSV file: {e}")
        return pd.DataFrame()
    
    if not df.empty:
        df.dropna(how='all', inplace=True)
        # Remove rows that contain 'WEEK' or 'Bibcode' in any column
        df = df[~df.apply(lambda row: row.astype(str).str.contains('WEEK', case=False).any(), axis=1)]
        df = df[~df.apply(lambda row: row.astype(str).str.contains('Bibcode', case=False).any(), axis=1)]
        df.reset_index(drop=True, inplace=True)
        df['Bibcode'] = df['Bibcode'].ffill()
        df['Pass Percentage'] = pd.to_numeric(df['Pass Percentage'], errors='coerce').fillna(0)
        df['Cases Passed'] = pd.to_numeric(df['Cases Passed'], errors='coerce').fillna(0)
        df['Cases Failed'] = pd.to_numeric(df['Cases Failed'], errors='coerce').fillna(0)
        # Convert 'PIP Used' to integer (assuming values are 1 or 0)
        df['PIP Used'] = pd.to_numeric(df['PIP Used'], errors='coerce').fillna(0).astype(int)
        # Ensure 'Updated Ubuntu Version' and 'Base Version' are strings and drop NaN values
        df['Updated Ubuntu Version'] = df['Updated Ubuntu Version'].astype(str)
        df['Base Version'] = df['Base Version'].astype(str)
        df = df[df['Updated Ubuntu Version'].notna()]
        df = df[df['Updated Ubuntu Version'].str.lower() != 'nan']
        df['Updated Ubuntu Version'] = df['Updated Ubuntu Version'].str.strip()
        df['Base Version'] = df['Base Version'].str.strip()
    return df

def preprocess_error_text(error_text):
    """Cleans and normalizes error messages for better grouping."""
    text = error_text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    return text

def get_top_error_groups(df, top_n=5):
    """Groups similar error messages and returns the top N most common errors."""
    error_messages_series = df['Error Details'].dropna().apply(lambda x: x.split(' and '))
    error_messages_list = [error.strip() for sublist in error_messages_series for error in sublist]
    # Preprocess each error message
    error_messages = [preprocess_error_text(error) for error in error_messages_list]
    
    if len(error_messages) == 0:
        print("No error messages found.")
        return pd.DataFrame(columns=['Error Group', 'Occurrences'])
    
    # Vectorize the error messages for similarity comparison
    vectorizer = TfidfVectorizer(stop_words='english')
    X = vectorizer.fit_transform(error_messages)
    
    # Clustering based on similarity
    clustering = AgglomerativeClustering(n_clusters=None, distance_threshold=0.5, metric='cosine', linkage='average')
    clusters = clustering.fit_predict(X.toarray())
    
    # Map errors to their clusters and count occurrences
    cluster_map = {error: cluster for error, cluster in zip(error_messages, clusters)}
    error_counts = Counter(clusters)
    top_clusters = error_counts.most_common(top_n)
    
    top_errors = []
    for cluster_id, count in top_clusters:
        clustered_errors = [error for error, cluster in cluster_map.items() if cluster == cluster_id]
        main_error_example = clustered_errors[0]
        top_errors.append({'Error Group': main_error_example, 'Occurrences': count})
    
    top_errors_df = pd.DataFrame(top_errors)
    return top_errors_df

def plot_top_errors(ax, df, top_n=5):
    """Plots the top N error groups as a horizontal bar chart."""
    top_errors_df = get_top_error_groups(df, top_n)
    
    if top_errors_df.empty:
        ax.text(0.5, 0.5, 'No Error Messages to Display', horizontalalignment='center', verticalalignment='center', fontsize=12)
        ax.axis('off')
        return
    
    bars = ax.barh(top_errors_df['Error Group'], top_errors_df['Occurrences'], color='skyblue')
    ax.set_xlabel('Number of Occurrences', fontsize=12)
    ax.set_title(f'Top {top_n} Error Groups', fontsize=14)
    ax.invert_yaxis()
    
    for bar in bars:
        width = bar.get_width()
        ax.annotate(f'{width}',
                    xy=(width, bar.get_y() + bar.get_height() / 2),
                    xytext=(5, 0), 
                    textcoords="offset points",
                    ha='left', va='center', fontsize=9)

def categorize_reproducibility(df):
    """Categorizes reproducibility at both row and (Bibcode, Ubuntu Version) level."""
    def categorize_row(row):
        if row['Pass Percentage'] == 0:
            return 'Non-Reproducible'
        elif pd.isna(row['Modifications to Dockerfile']) or row['Modifications to Dockerfile'].strip() == '':
            return 'Automatic Reproducible'
        else:
            return 'Reproducible with Effort'

    df['Reproducibility'] = df.apply(categorize_row, axis=1)

    # Group by both Bibcode and Updated Ubuntu Version
    def categorize_group(group):
        if (group == 'Non-Reproducible').any():
            return 'Non-Reproducible'
        elif (group == 'Reproducible with Effort').any():
            return 'Reproducible with Effort'
        else:
            return 'Automatic Reproducible'

    df['Group Reproducibility'] = df.groupby(['Bibcode', 'Updated Ubuntu Version'])['Reproducibility'].transform(categorize_group)

    return df

def plot_bibcode_counts_by_category(ax, df):
    """Plots the count of bibcodes per reproducibility category by Ubuntu version with specified colors."""

    df_unique = df[['Bibcode', 'Updated Ubuntu Version', 'Group Reproducibility']].drop_duplicates()
    df_unique = df_unique.dropna(subset=['Updated Ubuntu Version'])
    
    categories = df_unique['Group Reproducibility'].unique()
    expected_categories = ['Automatic Reproducible', 'Reproducible with Effort', 'Non-Reproducible']
    categories = [cat for cat in expected_categories if cat in categories]
    
    counts_per_version = df_unique.groupby(['Updated Ubuntu Version', 'Group Reproducibility']).size().unstack(fill_value=0)
    counts_per_version = counts_per_version.reindex(columns=categories, fill_value=0)
    counts_per_version_sorted = counts_per_version.sort_index()
    
    colors = {'Automatic Reproducible': 'green', 'Reproducible with Effort': 'blue', 'Non-Reproducible': 'red'}
    plot_colors = [colors.get(col, 'grey') for col in counts_per_version_sorted.columns]
    
    counts_per_version_sorted.plot(kind='bar', stacked=False, ax=ax, color=plot_colors)
    
    ax.yaxis.get_major_locator().set_params(integer=True)
    
    for container in ax.containers:
        ax.bar_label(container, label_type='edge')
    
    ax.set_xlabel('Ubuntu Version', fontsize=12)
    ax.set_ylabel('Number of Articles', fontsize=12)
    ax.set_title('Counts of Articles per Reproducibility Category per Ubuntu Version', fontsize=14)
    ax.legend(title='Reproducibility Category')
    ax.tick_params(axis='x', rotation=45)

def plot_bibcode_counts_by_base_and_category(df):
    """Plots the count of bibcodes per reproducibility category by Ubuntu base and updated versions in a grid."""
    
    df_unique = df[['Bibcode', 'Base Version', 'Updated Ubuntu Version', 'Group Reproducibility']].drop_duplicates()
    df_unique = df_unique.dropna(subset=['Updated Ubuntu Version', 'Base Version'])
    
    # Get the list of base versions
    base_versions = df_unique['Base Version'].unique()
    base_versions = sorted(base_versions)
    
    colors = {'Automatic Reproducible': 'green', 'Reproducible with Effort': 'blue', 'Non-Reproducible': 'red'}
    expected_categories = ['Automatic Reproducible', 'Reproducible with Effort', 'Non-Reproducible']
    
    num_base_versions = len(base_versions)
    num_cols = 2
    num_rows = math.ceil(num_base_versions / num_cols)
    total_plots = num_rows * num_cols
    
    fig, axes = plt.subplots(nrows=num_rows, ncols=num_cols, figsize=(8 * num_cols, 5 * num_rows))
    axes = axes.flatten()
    
    for idx, (ax, base_version) in enumerate(zip(axes, base_versions)):
        subset = df_unique[df_unique['Base Version'] == base_version]
        if subset.empty:
            ax.axis('off')
            continue
        
        counts_per_version = subset.groupby(['Updated Ubuntu Version', 'Group Reproducibility']).size().unstack(fill_value=0)
        counts_per_version = counts_per_version.reindex(columns=expected_categories, fill_value=0)
        counts_per_version = counts_per_version.sort_index()
        
        plot_colors = [colors.get(col, 'grey') for col in counts_per_version.columns]
        
        counts_per_version.plot(kind='bar', stacked=False, ax=ax, color=plot_colors)
        
        ax.yaxis.get_major_locator().set_params(integer=True)
        
        for container in ax.containers:
            ax.bar_label(container, label_type='edge')
        
        ax.set_xlabel('Updated Ubuntu Version', fontsize=12)
        ax.set_ylabel('Number of Articles', fontsize=12)
        ax.set_title(f'Base Version {base_version}', fontsize=14)
        ax.legend(title='Reproducibility Category')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    
    # Hide any unused subplots
    if num_base_versions < total_plots:
        for idx in range(num_base_versions, total_plots):
            axes[idx].axis('off')
    
    plt.suptitle('Counts of Articles per Reproducibility Category by Base and Updated Ubuntu Versions', fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()


def plot_avg_pass_percentage(ax, df):
    """Plots the average pass percentage per Ubuntu version with drop annotations and knee point detection."""
    avg_pass_percentage = df.groupby('Updated Ubuntu Version')['Pass Percentage'].mean().reset_index()
    avg_pass_percentage_sorted = avg_pass_percentage.sort_values(by='Updated Ubuntu Version')
    avg_pass_percentage_sorted['Pass Percentage Change'] = avg_pass_percentage_sorted['Pass Percentage'].diff()
    
    if avg_pass_percentage_sorted['Pass Percentage Change'].isnull().all():
        print("Not enough data to calculate pass percentage changes.")
        knee_point = pd.Series({'Updated Ubuntu Version': avg_pass_percentage_sorted.iloc[0]['Updated Ubuntu Version'],
                                'Pass Percentage': avg_pass_percentage_sorted.iloc[0]['Pass Percentage'],
                                'Pass Percentage Change': 0})
    else:
        knee_point = avg_pass_percentage_sorted.loc[avg_pass_percentage_sorted['Pass Percentage Change'].idxmin()]
    
    # Identify knee point details
    knee_version = knee_point['Updated Ubuntu Version']
    knee_drop = knee_point['Pass Percentage Change']
    
    print(f"\nKnee Point Detected:")
    print(f"Ubuntu Version: {knee_version}")
    print(f"Pass Percentage Drop: {knee_drop:.2f}%")
    
    # Calculate drop percentages for all versions
    avg_pass_percentage_sorted['Drop Percentage'] = avg_pass_percentage_sorted['Pass Percentage Change']
    
    drop_percentages = avg_pass_percentage_sorted['Drop Percentage'].tolist()
    ubuntu_versions = avg_pass_percentage_sorted['Updated Ubuntu Version'].tolist()
    pass_percentages = avg_pass_percentage_sorted['Pass Percentage'].tolist()
    
    # Plotting Average Pass Percentage per Ubuntu Version
    ax.plot(
        ubuntu_versions,
        pass_percentages,
        marker='o',
        linestyle='-',
        color='green',
        label='Average Pass Percentage'
    )
    
    # Annotate each Ubuntu version with its drop percentage from the previous version
    for i in range(1, len(ubuntu_versions)):
        version = ubuntu_versions[i]
        drop = drop_percentages[i]
        pass_pct = pass_percentages[i]
        ax.annotate(
            f"{drop:+.1f}%",
            xy=(version, pass_pct),
            xytext=(0, 10),
            textcoords='offset points',
            ha='center',
            va='bottom',
            fontsize=9,
            color='red',
            arrowprops=dict(arrowstyle='->', color='red', lw=0.5)
        )
    
    # Highlight the knee point
    ax.plot(
        knee_version,
        knee_point['Pass Percentage'],
        marker='D',
        markersize=10,
        color='red',
        label='Knee Point'
    )
    ax.annotate(
        f"Knee: {knee_version}\n",
        xy=(knee_version, knee_point['Pass Percentage']),
        xytext=(0, 10),
        textcoords='offset points',
        ha='center',
        va='bottom',
        fontsize=9,
        arrowprops=dict(facecolor='black', arrowstyle='->')
    )
    
    ax.set_xlabel('Ubuntu Version', fontsize=12)
    ax.set_ylabel('Average Pass Percentage (%)', fontsize=12)
    ax.set_title('Average Pass Percentage per Ubuntu Version with Drop Percentages', fontsize=14)
    ax.set_xticks(range(len(ubuntu_versions)))
    ax.set_xticklabels(ubuntu_versions, rotation=45)
    ax.set_ylim(0, 100)
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    ax.legend()

def plot_pass_percentage_by_pip(ax, df):
    """Plots the average pass percentage per Ubuntu version, comparing PIP Used vs Not Used, with percentage annotations."""
    avg_pass_pct_pip = df.groupby(['Updated Ubuntu Version', 'PIP Used'])['Pass Percentage'].mean().reset_index()
    avg_pass_pct_pip_pivot = avg_pass_pct_pip.pivot(index='Updated Ubuntu Version', columns='PIP Used', values='Pass Percentage')
    
    avg_pass_pct_pip_pivot = avg_pass_pct_pip_pivot.sort_index()
    
    avg_pass_pct_pip_pivot.plot(kind='line', marker='o', ax=ax)
    
    ax.set_xlabel('Ubuntu Version', fontsize=12)
    ax.set_ylabel('Average Pass Percentage (%)', fontsize=12)
    ax.set_title('Average Pass Percentage per Ubuntu Version (PIP Used vs Not Used)', fontsize=14)
    ax.set_xticks(range(len(avg_pass_pct_pip_pivot.index)))
    ax.set_xticklabels(avg_pass_pct_pip_pivot.index, rotation=45)
    ax.set_ylim(0, 100)
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    pip_used_labels = {0: 'No', 1: 'Yes'}
    pip_used_values = avg_pass_pct_pip_pivot.columns.tolist()
    ax.legend(title='PIP Used', labels=[pip_used_labels.get(pip_used, str(pip_used)) for pip_used in pip_used_values])
    
    for pip_used in avg_pass_pct_pip_pivot.columns:
        y_values = avg_pass_pct_pip_pivot[pip_used].values
        x_values = range(len(avg_pass_pct_pip_pivot.index))
        for x, y in zip(x_values, y_values):
            if not pd.isna(y):
                ax.annotate(f"{y:.1f}%", xy=(x, y), xytext=(0, 5), textcoords='offset points', ha='center', fontsize=9)

def plot_reproducibility_by_pip_and_version(df):
    """Plots the counts of reproducibility types for PIP Used vs Not Used per Ubuntu version in separate subplots."""
    colors = {'Automatic Reproducible': 'green', 'Reproducible with Effort': 'blue', 'Non-Reproducible': 'red'}

    df_unique = df[['Bibcode', 'PIP Used', 'Updated Ubuntu Version', 'Group Reproducibility']].drop_duplicates()

    counts = df_unique.groupby(['Updated Ubuntu Version', 'PIP Used', 'Group Reproducibility']).size().reset_index(name='Counts')

    expected_categories = ['Automatic Reproducible', 'Reproducible with Effort', 'Non-Reproducible']

    pip_used_labels = {0: 'No', 1: 'Yes'}
    counts['PIP Used'] = counts['PIP Used'].map(pip_used_labels)

    fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(16, 7), sharey=True)

    for i, pip_used in enumerate(['Yes', 'No']):
        ax = axes[i]
        subset = counts[counts['PIP Used'] == pip_used]
        pivot_table = subset.pivot(index='Updated Ubuntu Version', columns='Group Reproducibility', values='Counts').fillna(0)
        pivot_table = pivot_table.reindex(columns=expected_categories, fill_value=0)
        pivot_table.plot(kind='bar', stacked=False, ax=ax, color=[colors.get(c) for c in expected_categories])

        ax.set_title(f'Reproducibility Categories - PIP {pip_used}', fontsize=14)
        ax.set_xlabel('Ubuntu Version', fontsize=12)
        if i == 0:
            ax.set_ylabel('Number of Articles', fontsize=12)
        else:
            ax.set_ylabel('')
        ax.legend(title='Reproducibility Category')
        ax.tick_params(axis='x', rotation=45)
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)

        for container in ax.containers:
            ax.bar_label(container, fmt='%d', fontsize=8)

    fig.suptitle('Counts of Articles per Reproducibility Category per Ubuntu Version', fontsize=16)
    plt.tight_layout(rect=[0, 0, 1, 0.95])

def main():
    # Load and clean data
    df = load_and_clean_data(csv_file)

    # Check if data is loaded
    if df.empty:
        print("No data to process.")
        return

    # Categorize reproducibility
    df = categorize_reproducibility(df)

    # Print counts per category per Ubuntu version
    print("Counts of Bibcodes in each category per Ubuntu version:")
    counts = df[['Bibcode', 'Updated Ubuntu Version', 'Group Reproducibility']].drop_duplicates()
    counts = counts.groupby(['Updated Ubuntu Version', 'Group Reproducibility']).size().unstack(fill_value=0)
    print(counts)

    ### Plot 1a ###
    fig1a, ax1a = plt.subplots(figsize=(12, 7))

    # Plot Average Pass Percentage per Ubuntu Version
    plot_avg_pass_percentage(ax1a, df)

    fig1a.tight_layout()

    ### Plot 1b ###
    fig1b, ax1b = plt.subplots(figsize=(12, 7))

    # Plot Counts of Bibcodes per Reproducibility Category per Ubuntu Version
    plot_bibcode_counts_by_category(ax1b, df)

    fig1b.tight_layout()

    ### Plot 2 ###
    fig2, ax2 = plt.subplots(figsize=(12, 7))

    # Plot Top 5 Error Groups on the second figure
    plot_top_errors(ax2, df, top_n=5)

    fig2.tight_layout()

    ### Plot 3 ###
    fig3, ax3 = plt.subplots(figsize=(12, 7))

    # Plot Average Pass Percentage per Ubuntu Version for PIP Used vs Not Used, with annotations
    plot_pass_percentage_by_pip(ax3, df)

    fig3.tight_layout()

    ### Plot 4 ###
    # Plot Reproducibility Categories by PIP Used per Ubuntu Version
    plot_reproducibility_by_pip_and_version(df)

    ### Plot 5 ###
    # Plot Counts by Base Version, Updated Ubuntu Version, and Reproducibility Category
    plot_bibcode_counts_by_base_and_category(df)

    # Display the plots
    plt.show()

if __name__ == '__main__':
    main()

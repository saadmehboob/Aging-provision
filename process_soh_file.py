# ipnb.py
import pandas as pd
import numpy as np
import re
from io import BytesIO

def season_sort_key(season):
    if not isinstance(season, str) or len(season) < 4:
        return (0, 0)
    season_type = season[:2]
    year = int(season[-2:])
    season_rank = 1 if season_type == "AW" else 0
    return (year, season_rank)

def standardize_season(raw_season):
    if not isinstance(raw_season, str) or raw_season.strip() == "":
        return "Unknown"
    season = raw_season.strip().upper()
    if "CONTINUITY" in season or "BASICS" in season:
        return "Continuity"
    elif "OLD" in season:
        return "Old-"
    year_match = re.search(r"(20\d{2})", season)
    if year_match:
        year = year_match.group(1)[2:]
        if any(tag in season for tag in ["SPRING", "SUMMER", "SS"]):
            return f"SS{year}"
        elif any(tag in season for tag in ["AUTUMN", "WINTER", "AW"]):
            return f"AW{year}"
    match = re.search(r"(SS|AW)(\d{2})", season)
    if match:
        return f"{match.group(1)}{match.group(2)}"
    match = re.search(r"WA(\d{2})", season)
    if match:
        return f"AW{match.group(1)}"
    match = re.search(r"(\d{2})", season)
    if match:
        return f"SS{match.group(1)}"
    return "Unknown"

def process_soh_file(soh_io, first_bucket_seasons, damage_pct, leftover_running_pct,
                     leftover_closed_pct, closed_pct, brand_override, current_balance_io):
    soh = pd.read_excel(soh_io, sheet_name='Sheet1')
    soh = soh[(soh['GROUP_NAME'] != 'Aleph') & (soh['AR Comments'] == 'Consider')]
    mapping = pd.read_excel('Mapping & Combinations/mapping.xlsx')
    combinations = pd.read_excel('Mapping & Combinations/combinations.xlsx')
    existing_balances = pd.read_excel(current_balance_io) if current_balance_io else pd.DataFrame(columns=['s1','s2','s3','s4','Closing balance'])

    soh['NETTOTAL_COST'].fillna(0, inplace=True)
    soh['NETTOTAL_COST'] = pd.to_numeric(soh['NETTOTAL_COST'], errors='coerce')

    original_season = 'SEASON_DESC' if 'SEASON_DESC' in soh.columns else 'SEASON DESC'
    soh['GROUP_NAME'] = soh['GROUP_NAME'].str.upper()
    mapping['GROUP_NAME'] = mapping['GROUP_NAME'].str.upper()
    soh = soh.merge(mapping, on='GROUP_NAME', how='left')
    soh = soh[soh['Closed_status'] != 'Exit']
    soh['std_season'] = soh[original_season].apply(standardize_season)

    excluded = {'Unknown', 'Continuity', 'Old-', 'AW97'}
    sorted_seasons = sorted([s for s in soh['std_season'].unique() if s not in excluded], key=season_sort_key, reverse=True)
    b1 = sorted_seasons[:first_bucket_seasons]
    b2 = sorted_seasons[first_bucket_seasons:first_bucket_seasons + 3]
    b3 = sorted_seasons[first_bucket_seasons+3:first_bucket_seasons + 6]
    b4 = sorted_seasons[first_bucket_seasons + 6:]
    b1 += ['Unknown','Continuity']
    b4 += ['Old-','AW97']

    soh['season_bucket'] = np.select([
        soh['std_season'].isin(b1),
        soh['std_season'].isin(b2),
        soh['std_season'].isin(b3)
    ], ['bucket1','bucket2','bucket3'], default='bucket4')

    soh['Continuity_factor'] = 0.40
    soh['provision_%_policy'] = soh['season_bucket'].map({
        'bucket1': 0,
        'bucket2': 0.15,
        'bucket3': 0.50,
        'bucket4': 0.75
    })

    soh.loc[soh['Model'].isin(['Consignment','Guaranteed Margin','Buying Pull - Mango']),
            ['provision_amount_policy', 'provision_%_policy', 'Continuity_factor']] = 0
    soh['provision_amount_policy'] = soh['NETTOTAL_COST'] * soh['provision_%_policy'] * soh['Continuity_factor']

    soh['location_catergory'] = "Store, Online & WH"
    soh.loc[soh['LOCATION_NAME'].str.lower().str.contains('leftover'), 'location_catergory'] = 'Leftover'
    soh.loc[soh['LOCATION_NAME'].str.lower().str.contains('damage'), 'location_catergory'] = 'Damage'
    soh.loc[soh['LOCATION_NAME'].str.lower().str.contains('sulay'), 'location_catergory'] = 'Leftover'

    soh['additional_provision'] = 0
    soh.loc[soh['location_catergory'] == 'Damage', 'additional_provision'] = soh['NETTOTAL_COST'] * damage_pct - soh['provision_amount_policy']

    closed = soh['Closed_status'] == 'Closed'
    leftover = soh['location_catergory'] == 'Leftover'
    damage = soh['location_catergory'] == 'Damage'
    soh.loc[closed & leftover, 'additional_provision'] = soh['NETTOTAL_COST'] * leftover_closed_pct - soh['provision_amount_policy']
    soh.loc[~closed & leftover, 'additional_provision'] = soh['NETTOTAL_COST'] * leftover_running_pct - soh['provision_amount_policy']
    soh.loc[closed & ~(leftover | damage), 'additional_provision'] = soh['NETTOTAL_COST'] * closed_pct - soh['provision_amount_policy']

    if brand_override:
        soh['additional_provision'] = np.where(
            soh['Std Brand'].isin(brand_override.keys()),
            soh['NETTOTAL_COST'] * soh['Std Brand'].map(brand_override) - soh['provision_amount_policy'],
            soh['additional_provision']
        )

    soh.loc[soh['Model'].isin(['Consignment','Guaranteed Margin','Buying Pull - Mango']),
            ['provision_amount_policy', 'provision_%_policy', 'Continuity_factor','additional_provision']] = 0
    soh['provision_amount_policy'].fillna(0, inplace=True)
    soh['additional_provision'].fillna(0, inplace=True)
    soh['Total Provision'] = soh['provision_amount_policy'] + soh['additional_provision']

    summary = soh.groupby('Std Brand')[['NETTOTAL_COST','provision_amount_policy','additional_provision','Total Provision']].sum()
    summary['coverage'] = summary['Total Provision'] / summary['NETTOTAL_COST']

    soh_comb = soh.merge(combinations, on=['Std Brand','LOCATION'], how='left')
    soh_comb[['s1', 's2', 's3', 's4']] = soh_comb[['s1', 's2', 's3', 's4']].fillna(0)

    entry = soh_comb.groupby(['s1','s2','s3','s4'])['Total Provision'].sum().reset_index().fillna(0)
    entry['s5'] = 63002
    entry2 = entry.copy()
    entry2['Total Provision'] *= -1
    entry2['s5'] = 23993
    completed_entry = pd.concat([entry, entry2], ignore_index=True)
    completed_entry.rename(columns={'Total Provision': 'Dr/(CR)'}, inplace=True)
    completed_entry = completed_entry[completed_entry['Dr/(CR)'] != 0]

    diff_table = soh_comb.groupby(['s1','s2','s3','s4'])['Total Provision'].sum().reset_index().fillna(0).merge(existing_balances, on=['s1','s2','s3','s4'], how='outer').fillna(0)
    diff_table['Dr/(CR)'] = -(diff_table['Total Provision'] + diff_table['Closing balance'])
    diff_table.drop(['Closing balance','Total Provision'], axis=1, inplace=True)
    diff_table['s5'] = 23993
    diff_table2 = diff_table.copy()
    diff_table2['Dr/(CR)'] *= -1
    diff_table2['s5'] = 63002
    diff_entry = pd.concat([diff_table, diff_table2], ignore_index=True)
    diff_entry = diff_entry[diff_entry['Dr/(CR)'] != 0]

    damage_summary = soh_comb[soh_comb['location_catergory'] == 'Damage'].groupby('Std Brand')[['NETTOTAL_COST','Total Provision']].sum()
    damage_summary['coverage'] = damage_summary['Total Provision'] / damage_summary['NETTOTAL_COST']
    leftover_summary = soh_comb[soh_comb['location_catergory'] == 'Leftover'].groupby('Std Brand')[['NETTOTAL_COST','Total Provision']].sum()
    leftover_summary['coverage'] = leftover_summary['Total Provision'] / leftover_summary['NETTOTAL_COST']
    closed_summary = soh_comb[soh_comb['Closed_status'] == 'Closed'].groupby('Std Brand')[['NETTOTAL_COST','Total Provision']].sum()
    closed_summary['coverage'] = closed_summary['Total Provision'] / closed_summary['NETTOTAL_COST']

    check_buckets = soh[['season_bucket','std_season']].drop_duplicates()
    check_season = soh[['std_season', original_season]].drop_duplicates()
    missing_combinations = soh_comb[(soh_comb['NETTOTAL_COST'] != 0) & (soh_comb['s1'].isna())]

    return {
        'summary': summary,
        'provision_csv': soh.to_csv(index=False).encode(),
        'diff_csv': diff_entry.to_csv(index=False).encode(),
        'checks': {
            'check_buckets': check_buckets,
            'check_season': check_season,
            'missing_combinations': missing_combinations
        },
        'damage_summary': damage_summary,
        'leftover_summary': leftover_summary,
        'closed_summary': closed_summary,
        'diff_entry': diff_entry
    }

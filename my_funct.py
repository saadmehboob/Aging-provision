import pandas as pd
import numpy as np
import os
import re

def run_aging_provision_pipeline(
    soh_path,
    mapping_path,
    combinations_path,
    balance_path,
    output_dir="Output",
    first_first_bucket_number_seasons=5,
    damage_percentage=1.0,
    leftover_running_percentage=0.15,
    leftover_closed_percentage=0.5,
    closed_percentage=0.5,
    brand_specific_provision=None,
):
    brand_specific_provision = brand_specific_provision or {}
    pd.options.display.float_format = '{:,.2f}'.format
    os.makedirs(output_dir, exist_ok=True)

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
        if "WA" in season:
            match = re.search(r"WA(\d{2})", season)
            if match:
                return f"AW{match.group(1)}"
        match = re.search(r"(\d{2})", season)
        if match:
            return f"SS{match.group(1)}"
        return "Unknown"

    soh = pd.read_excel(soh_path)
    soh = soh[(soh['GROUP_NAME'] != 'Aleph') & (soh['AR Comments'] == 'Consider')]
    existing_balances = pd.read_excel(balance_path)
    mapping = pd.read_excel(mapping_path)
    combinations = pd.read_excel(combinations_path).groupby(['LOCATION', 'Std Brand']).first().reset_index()

    soh['NETTOTAL_COST'].fillna(0, inplace=True)
    soh['NETTOTAL_COST'] = pd.to_numeric(soh['NETTOTAL_COST'], errors='coerce')
    original_season = 'SEASON_DESC' if 'SEASON_DESC' in soh.columns else 'SEASON DESC'
    soh['GROUP_NAME'] = soh['GROUP_NAME'].str.upper()
    mapping['GROUP_NAME'] = mapping['GROUP_NAME'].str.upper()
    soh = soh.merge(mapping, on='GROUP_NAME', how='left')
    soh = soh[(soh['Closed_status'] != 'Exit')]
    soh['std_season'] = soh[original_season].apply(standardize_season)

    excluded = {'Unknown', 'Continuity', 'Old-', 'AW97'}
    unique_season = [f for f in soh['std_season'].dropna().unique() if f not in excluded]
    sorted_std_season_in_soh = sorted(unique_season, key=season_sort_key, reverse=True)

    bucket1 = sorted_std_season_in_soh[:first_first_bucket_number_seasons] + ['Unknown', 'Continuity']
    bucket2 = sorted_std_season_in_soh[first_first_bucket_number_seasons:first_first_bucket_number_seasons + 3]
    bucket3 = sorted_std_season_in_soh[first_first_bucket_number_seasons + 3:first_first_bucket_number_seasons + 6]
    bucket4 = sorted_std_season_in_soh[first_first_bucket_number_seasons + 6:] + ['Old-', 'AW97']

    conditions = [
        soh['std_season'].isin(bucket1),
        soh['std_season'].isin(bucket2),
        soh['std_season'].isin(bucket3)
    ]
    soh['season_bucket'] = np.select(conditions, ['bucket1', 'bucket2', 'bucket3'], default='bucket4')
    soh['Continuity_factor'] = 0.40
    soh['provision_%_policy'] = soh['season_bucket'].map({'bucket1': 0, 'bucket2': 0.15, 'bucket3': 0.50, 'bucket4': 0.75})
    soh.loc[soh['Model'].isin(['Consignment', 'Guaranteed Margin', 'Buying Pull - Mango']),
            ['provision_amount_policy', 'provision_%_policy', 'Continuity_factor']] = 0
    soh['provision_amount_policy'] = soh['NETTOTAL_COST'] * soh['provision_%_policy'] * soh['Continuity_factor']

    soh['location_catergory'] = "Store, Online & WH"
    soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('leftover', na=False), "location_catergory"] = "Leftover"
    soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('damage', na=False), "location_catergory"] = "Damage"
    soh.loc[soh['LOCATION_NAME'].astype(str).str.lower().str.contains('sulay', na=False), "location_catergory"] = "Leftover"

    soh['additional_provision'] = 0
    soh.loc[soh['location_catergory'] == "Damage", 'additional_provision'] = (
        soh["NETTOTAL_COST"] * damage_percentage - soh['provision_amount_policy'])

    condition = (soh['Closed_status'] == "Closed") & (soh['location_catergory'] == "Leftover")
    soh.loc[condition, 'additional_provision'] = (
        soh["NETTOTAL_COST"] * leftover_closed_percentage - soh['provision_amount_policy'])

    condition = (soh['Closed_status'] != "Closed") & (soh['location_catergory'] == "Leftover")
    soh.loc[condition, 'additional_provision'] = (
        soh["NETTOTAL_COST"] * leftover_running_percentage - soh['provision_amount_policy'])

    condition = (soh['Closed_status'] == "Closed") & (~soh['location_catergory'].isin(["Leftover", "Damage"]))
    soh.loc[condition, 'additional_provision'] = (
        soh["NETTOTAL_COST"] * closed_percentage - soh['provision_amount_policy'])

    if brand_specific_provision:
        soh['additional_provision'] = np.where(
            soh['Std Brand'].isin(brand_specific_provision.keys()),
            soh['NETTOTAL_COST'] * soh['Std Brand'].map(brand_specific_provision) - soh['provision_amount_policy'],
            soh['additional_provision']
        )

    soh.loc[soh['Model'].isin(['Consignment', 'Guaranteed Margin', 'Buying Pull - Mango']),
            ['provision_amount_policy', 'provision_%_policy', 'Continuity_factor', 'additional_provision']] = 0

    soh['provision_amount_policy'] = soh['provision_amount_policy'].fillna(0)
    soh['additional_provision'] = soh['additional_provision'].fillna(0)
    soh['Total Provision'] = soh['provision_amount_policy'] + soh['additional_provision']
    soh.to_csv(os.path.join(output_dir, "aging_provision.csv"), index=False)

    # Generate analysis and checks
    soh_comb = soh.merge(combinations, on=['Std Brand', 'LOCATION'], how='left').fillna(0)
    soh_comb.to_excel(os.path.join(output_dir, "aging_provision_combinations.xlsx"), index=False)

    summary = soh_comb.groupby(by='Std Brand')[["NETTOTAL_COST", 'provision_amount_policy',
                                                 'additional_provision', 'Total Provision']].sum()
    summary['coverage'] = summary['Total Provision'] / summary['NETTOTAL_COST']

    entry = soh_comb.groupby(["s1", "s2", "s3", "s4"])['Total Provision'].sum().reset_index().fillna(0)
    entry['s5'] = 63002
    entry2 = entry.copy()
    entry2['Total Provision'] *= -1
    entry2['s5'] = 23993
    completed_entry = pd.concat([entry, entry2], ignore_index=True)
    completed_entry.rename(columns={'Total Provision': 'Dr/(CR)'}, inplace=True)
    completed_entry = completed_entry[completed_entry['Dr/(CR)'] != 0]
    completed_entry.to_csv(os.path.join(output_dir, "completed_entry.csv"), index=False)

    diff_table = soh_comb.groupby(["s1", "s2", "s3", "s4"])['Total Provision'].sum().reset_index().fillna(0)
    diff_table = diff_table.merge(existing_balances, on=['s1', 's2', 's3', 's4'], how='outer').fillna(0)
    diff_table['Dr/(CR)'] = (diff_table['Total Provision'] + diff_table['Closing balance']) * -1
    diff_table.drop(['Closing balance', 'Total Provision'], axis=1, inplace=True)

    diff_table['s5'] = 23993
    diff_table2 = diff_table.copy()
    diff_table2['Dr/(CR)'] *= -1
    diff_table2['s5'] = 63002
    diff_entry = pd.concat([diff_table, diff_table2], ignore_index=True)
    diff_entry = diff_entry[diff_entry['Dr/(CR)'] != 0]
    diff_entry.to_csv(os.path.join(output_dir, "diff_entry.csv"), index=False)

    return {
        "soh": soh,
        "summary": summary,
        "soh_comb": soh_comb,
        "completed_entry": completed_entry,
        "diff_entry": diff_entry
    }


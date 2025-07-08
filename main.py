import os
import requests
import csv
from io import StringIO
import re
from datetime import datetime, timedelta, timezone
from clickhouse_driver import Client

APPSFLYER_TOKEN = os.environ.get('APPSFLYER_TOKEN')
APP_IDS = os.environ.get('APP_IDS', 'id1203171490,vn.ghn.app.giaohangnhanh').split(',')
CH_HOST = os.environ.get('CH_HOST')
CH_PORT = int(os.environ.get('CH_PORT', 9000))
CH_USER = os.environ.get('CH_USER')
CH_PASSWORD = os.environ.get('CH_PASSWORD')
CH_DATABASE = os.environ.get('CH_DATABASE')
CH_TABLE = os.environ.get('CH_TABLE')

APPSFLYER_TO_CH = {
    "Attributed Touch Type": "attributed_touch_type",
    "Attributed Touch Time": "attributed_touch_time",
    "Install Time": "install_time",
    "Event Time": "event_time",
    "Event Name": "event_name",
    "Partner": "partner",
    "Media Source": "media_source",
    "Campaign": "campaign",
    "Adset": "adset",
    "Ad": "ad",
    "Ad Type": "ad_type",
    "Contributor 1 Touch Type": "contributor_1_touch_type",
    "Contributor 1 Touch Time": "contributor_1_touch_time",
    "Contributor 1 Partner": "contributor_1_partner",
    "Contributor 1 Match Type": "contributor_1_match_type",
    "Contributor 1 Media Source": "contributor_1_media_source",
    "Contributor 1 Campaign": "contributor_1_campaign",
    "Contributor 1 Engagement Type": "contributor_1_engagement_type",
    "Contributor 2 Touch Type": "contributor_2_touch_type",
    "Contributor 2 Touch Time": "contributor_2_touch_time",
    "Contributor 2 Partner": "contributor_2_partner",
    "Contributor 2 Media Source": "contributor_2_media_source",
    "Contributor 2 Campaign": "contributor_2_campaign",
    "Contributor 2 Match Type": "contributor_2_match_type",
    "Contributor 2 Engagement Type": "contributor_2_engagement_type",
    "Contributor 3 Touch Type": "contributor_3_touch_type",
    "Contributor 3 Touch Time": "contributor_3_touch_time",
    "Contributor 3 Partner": "contributor_3_partner",
    "Contributor 3 Media Source": "contributor_3_media_source",
    "Contributor 3 Campaign": "contributor_3_campaign",
    "Contributor 3 Match Type": "contributor_3_match_type",
    "Contributor 3 Engagement Type": "contributor_3_engagement_type",
    "City": "city",
    "IP": "ip",
    "AppsFlyer ID": "appsflyer_id",
    "Customer User ID": "customer_user_id",
    "IDFA": "idfa",
    "IDFV": "idfv",
    "Device Category": "device_category",
    "Platform": "platform",
    "OS Version": "os_version",
    "Bundle ID": "bundle_id",
    "Is Retargeting": "is_retargeting",
    "Attribution Lookback": "attribution_lookback",
    "Match Type": "match_type",
    "Device Download Time": "device_download_time",
    "Device Model": "device_model",
    "Engagement Type": "engagement_type"
}
ADDITIONAL_FIELDS = (
    'blocked_reason_rule,store_reinstall,impressions,contributor3_match_type,custom_dimension,conversion_type,'
    'gp_click_time,match_type,mediation_network,oaid,deeplink_url,blocked_reason,blocked_sub_reason,'
    'gp_broadcast_referrer,gp_install_begin,campaign_type,custom_data,rejected_reason,device_download_time,'
    'keyword_match_type,contributor1_match_type,contributor2_match_type,device_model,monetization_network,'
    'segment,is_lat,gp_referrer,blocked_reason_value,store_product_page,device_category,app_type,'
    'rejected_reason_value,ad_unit,keyword_id,placement,network_account_id,install_app_store,amazon_aid,att,'
    'engagement_type,gdpr_applies,ad_user_data_enabled,ad_personalization_enabled'
)
DATETIME_CH_COLS = {
    "attributed_touch_time", "install_time", "event_time",
    "contributor_1_touch_time", "contributor_2_touch_time",
    "contributor_3_touch_time", "device_download_time"
}

def parse_datetime(val):
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in ('', 'null', 'none', 'n/a'):
        return None
    if '.' in s:
        s = s.split('.')[0]
    match = re.match(r"^(\d{4}-\d{2}-\d{2}) (\d{1,2}):(\d{2}):(\d{2})$", s)
    if match:
        date_part, hour, minute, second = match.groups()
        hour = hour.zfill(2)
        s = f"{date_part} {hour}:{minute}:{second}"
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", s):
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    print(f"⚠️ DateTime sai định dạng: '{val}' -> set None")
    return None

def get_vn_time_range(hours=2):
    now_utc = datetime.now(timezone.utc)
    now_vn = now_utc + timedelta(hours=7)
    to_time = now_vn
    from_time = to_time - timedelta(hours=hours)
    return from_time.strftime('%Y-%m-%d %H:%M:%S'), to_time.strftime('%Y-%m-%d %H:%M:%S')

def download_appsflyer_events(app_id, from_time, to_time):
    url = (
        f"https://hq1.appsflyer.com/api/raw-data/export/app/{app_id}/organic_installs_report/v5"
        f"?from={from_time}&to={to_time}&timezone=Asia%2FHo_Chi_Minh"
        f"&additional_fields={ADDITIONAL_FIELDS}"
    )
    headers = {"Authorization": APPSFLYER_TOKEN, "accept": "text/csv"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        print(f"❌ Error ({app_id}):", resp.text)
        return []
    csvfile = StringIO(resp.text)
    reader = csv.DictReader(csvfile)
    reader.fieldnames = [h.strip('\ufeff') for h in reader.fieldnames]
    data = [row for row in reader]
    return data

def main():
    from_time, to_time = get_vn_time_range(2)
    print(f"🕒 Lấy AppsFlyer từ {from_time} đến {to_time} (Asia/Ho_Chi_Minh)")
    client = Client(
        host=CH_HOST, port=CH_PORT, user=CH_USER, password=CH_PASSWORD, database=CH_DATABASE
    )
    appsflyer_cols = list(APPSFLYER_TO_CH.keys())
    ch_cols = list(APPSFLYER_TO_CH.values())
    event_time_idx = ch_cols.index('event_time')
    bundle_id_idx = ch_cols.index('bundle_id') if 'bundle_id' in ch_cols else None

    total_inserted = 0

    for app_id in APP_IDS:
        app_id = app_id.strip()
        print(f"\n==== Processing APP_ID: {app_id} ====")
        # Lấy event_time lớn nhất đã insert của từng app_id
        result = client.execute(
            f"SELECT max(event_time) FROM {CH_TABLE} WHERE bundle_id='{app_id}'"
        )
        max_event_time = result[0][0] if result and result[0][0] else None
        if max_event_time:
            print(f"Max event_time đã có: {max_event_time}")
        else:
            print("Bảng trống hoặc chưa có event nào cho app này.")

        raw_data = download_appsflyer_events(app_id, from_time, to_time)
        if not raw_data:
            print(f"⚠️ Không có data AppsFlyer cho app {app_id} trong khoảng này.")
            continue

        mapped_data = []
        for row in raw_data:
            mapped_row = []
            for af_col, ch_col in zip(appsflyer_cols, ch_cols):
                val = row.get(af_col)
                if ch_col == "bundle_id":
                    mapped_row.append(app_id)
                elif ch_col in DATETIME_CH_COLS:
                    dt_val = parse_datetime(val)
                    mapped_row.append(dt_val)
                else:
                    mapped_row.append(val if val not in (None, "", "null", "None") else None)
            # Lọc ngay theo event_time
            if max_event_time:
                if mapped_row[event_time_idx] and mapped_row[event_time_idx] <= max_event_time:
                    continue  # skip old rows
            mapped_data.append(mapped_row)

        print(f"➕ Số dòng mới sẽ insert: {len(mapped_data)}")

        if mapped_data:
            client.execute(
                f"INSERT INTO {CH_TABLE} ({', '.join(ch_cols)}) VALUES",
                mapped_data
            )
            print(f"✅ Đã insert lên ClickHouse xong! ({len(mapped_data)} rows)")
            total_inserted += len(mapped_data)
        else:
            print("Không có dòng mới để insert.")

    client.disconnect()
    print(f"\n== Tổng số rows insert vào ClickHouse (cả các app): {total_inserted} ==")

if __name__ == "__main__":
    main()

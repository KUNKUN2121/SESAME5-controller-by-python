import asyncio
from bleak import BleakScanner
from bleak.backends.scanner import AdvertisementData
from bleak.backends.device import BLEDevice

# SESAMEの製造元であるCANDY HOUSE社のカンパニーID
# Cコードの 0x5A 0x05 は 0x055A のリトルエンディアン表現
SESAME_COMPANY_ID = 0x055A

async def main():
    print("SESAMEデバイスのスキャンを開始します... (Ctrl+Cで停止)")

    # スキャン中にデバイスが見つかるたびに呼び出されるコールバック関数
    def detection_callback(device: BLEDevice, advertisement_data: AdvertisementData):
        # アドバタイズデータにメーカー独自データが含まれているかチェック
        if SESAME_COMPANY_ID in advertisement_data.manufacturer_data:
            
            # メーカーデータを取得
            mfg_data = advertisement_data.manufacturer_data[SESAME_COMPANY_ID]
            
            # データの長さが十分か確認 (少なくともステータス情報まであるか)
            if len(mfg_data) < 3:
                return

            # Cコードの mfg_data[2] に相当 (デバイスID)
            device_id = mfg_data[0]
            
            # Cコードの mfg_data[4] に相当 (登録状態)
            # 0x00: 未登録, 0x01: 登録済み
            is_registered = mfg_data[2]

            if is_registered == 0x00:
                print(f"✅ 未登録のSESAMEを発見！")
                print(f"  - MACアドレス: {device.address}")
                print(f"  - デバイスID: {device_id}")
                # 修正点: device.rssi -> advertisement_data.rssi
                print(f"  - RSSI: {advertisement_data.rssi} dBm")
                print("-" * 20)
            else:
                print(f"ℹ️ 登録済みのSESAMEを発見")
                print(f"  - MACアドレス: {device.address}")
                print(f"  - デバイスID: {device_id}")
                # 修正点: device.rssi -> advertisement_data.rssi
                print(f"  - RSSI: {advertisement_data.rssi} dBm")
                print("-" * 20)


    # スキャナーを作成してスキャンを開始
    async with BleakScanner(detection_callback=detection_callback) as scanner:
        # スクリプトが動き続けるように長時間スリープ
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        # 非同期処理を実行
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nスキャンを停止しました。")
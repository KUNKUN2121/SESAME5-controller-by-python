from dataclasses import dataclass
import struct

@dataclass
class MechStatus:
    battery: int              # uint16_t
    target: int               # int16_t
    position: int             # int16_t
    is_clutch_failed: bool    # 1 bit
    is_lock_range: bool       # 1 bit
    is_unlock_range: bool     # 1 bit
    is_critical: bool         # 1 bit
    is_stop: bool             # 1 bit
    is_low_battery: bool      # 1 bit
    is_clockwise: bool        # 1 bit

    def __str__(self):
        return (f"MechStatus(battery={self.battery}, target={self.target}, position={self.position}, "
                f"is_clutch_failed={self.is_clutch_failed}, is_lock_range={self.is_lock_range}, "
                f"is_unlock_range={self.is_unlock_range}, is_critical={self.is_critical}, "
                f"is_stop={self.is_stop}, is_low_battery={self.is_low_battery}, "
                f"is_clockwise={self.is_clockwise})")

def parse_mech_status(decrypted_data: bytes) -> MechStatus:
    # 期待するデータ長は7バイト
    expected_length = 7
    if len(decrypted_data) < expected_length:
        raise ValueError(f"Decrypted data is too short: expected at least {expected_length} bytes, got {len(decrypted_data)} bytes")
    
    # struct.unpack でデータを解析
    battery, target, position, flags = struct.unpack('<HhhB', decrypted_data[:7])
    
    # フラグのビットを解析
    is_clutch_failed = bool(flags & 0x01)
    is_lock_range = bool((flags >> 1) & 0x01)
    is_unlock_range = bool((flags >> 2) & 0x01)
    is_critical = bool((flags >> 3) & 0x01)
    is_stop = bool((flags >> 4) & 0x01)
    is_low_battery = bool((flags >> 5) & 0x01)
    is_clockwise = bool((flags >> 6) & 0x01)
    
    return MechStatus(
        battery=battery,
        target=target,
        position=position,
        is_clutch_failed=is_clutch_failed,
        is_lock_range=is_lock_range,
        is_unlock_range=is_unlock_range,
        is_critical=is_critical,
        is_stop=is_stop,
        is_low_battery=is_low_battery,
        is_clockwise=is_clockwise
    )
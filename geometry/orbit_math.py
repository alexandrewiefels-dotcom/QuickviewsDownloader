# geometry/orbit_math.py
import math

EARTH_RADIUS_KM = 6371.0
MU = 398600.44  # Earth's gravitational parameter (km³/s²)


def altitude_from_mean_motion(mean_motion_rev_per_day):
    """
    Calculate satellite altitude from mean motion.
    
    Args:
        mean_motion_rev_per_day: Number of revolutions per day
    
    Returns:
        altitude in km
    """
    # Convert to revolutions per second
    mean_motion_rev_per_sec = mean_motion_rev_per_day / 86400.0
    
    # Calculate period in seconds
    period_sec = 1.0 / mean_motion_rev_per_sec
    
    # Calculate semi-major axis using Kepler's third law
    # T = 2π √(a³/μ)
    a = ((period_sec ** 2 * MU) / (4 * math.pi ** 2)) ** (1/3)
    
    # Altitude = semi-major axis - Earth radius
    altitude_km = a - EARTH_RADIUS_KM
    
    return altitude_km


def mean_motion_from_altitude(altitude_km):
    """
    Calculate mean motion from altitude.
    
    Args:
        altitude_km: Altitude in km
    
    Returns:
        mean motion in revolutions per day
    """
    a = EARTH_RADIUS_KM + altitude_km
    period_sec = 2 * math.pi * math.sqrt(a**3 / MU)
    mean_motion_rev_per_sec = 1.0 / period_sec
    mean_motion_rev_per_day = mean_motion_rev_per_sec * 86400
    return mean_motion_rev_per_day


# Test with known values
if __name__ == "__main__":
    # ISS: ~400km altitude, ~15.5 rev/day
    alt = altitude_from_mean_motion(15.5)
    print(f"Altitude from mean motion 15.5: {alt:.0f} km")
    
    mm = mean_motion_from_altitude(400)
    print(f"Mean motion from altitude 400km: {mm:.2f} rev/day")

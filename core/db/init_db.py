import logging
import os
from core.db.profile_manager import ProfileManager

logger = logging.getLogger(__name__)

def populate_gost_8732(manager: ProfileManager):
    # ... (same content as before)
    pipes = [
        ("57x3", 57, 3, 3.99, 5.09, 18.8, 6.59, 1.92),
        ("57x3.5", 57, 3.5, 4.62, 5.88, 21.4, 7.52, 1.91),
        ("57x4", 57, 4, 5.23, 6.66, 23.9, 8.39, 1.89),
        ("76x3", 76, 3, 5.40, 6.88, 46.7, 12.3, 2.61),
        ("76x3.5", 76, 3.5, 6.26, 7.97, 53.5, 14.1, 2.59),
        ("76x4", 76, 4, 7.10, 9.05, 60.1, 15.8, 2.58),
        ("89x3.5", 89, 3.5, 7.38, 9.40, 88.1, 19.8, 3.06),
        ("89x4", 89, 4, 8.38, 10.7, 99.4, 22.3, 3.05),
        ("108x4", 108, 4, 10.26, 13.1, 182, 33.7, 3.73),
        ("133x4", 133, 4, 12.73, 16.2, 343, 51.6, 4.60),
        ("159x4.5", 159, 4.5, 17.15, 21.8, 663, 83.4, 5.51),
        ("219x6", 219, 6, 31.52, 40.1, 2324, 212, 7.61),
        ("273x7", 273, 7, 45.92, 58.5, 5308, 389, 9.53),
        ("325x8", 325, 8, 62.54, 79.7, 10220, 629, 11.3),
    ]

    for p in pipes:
        designation, d, t, mass, A, Ix, Wx, i = p
        data = {
            "standard": "GOST 8732-78",
            "type": "pipe",
            "designation": designation,
            "d": d,
            "t": t,
            "mass_per_m": mass,
            "A": A,
            "Ix": Ix,
            "Iy": Ix,
            "Wx": Wx,
            "Wy": Wx,
            "i_x": i,
            "i_y": i
        }
        manager.add_profile(data)
    logger.info(f"Added {len(pipes)} profiles for GOST 8732-78")

def populate_gost_8509(manager: ProfileManager):
    # ... (same content as before)
    angles = [
        ("40x4", 40, 4, 1.2, 3.08, 2.42, 4.53, 1.21),
        ("50x5", 50, 5, 1.5, 4.80, 3.77, 11.2, 1.53),
        ("63x5", 63, 5, 1.8, 6.13, 4.81, 23.2, 1.95),
        ("63x6", 63, 6, 1.8, 7.28, 5.72, 27.3, 1.94),
        ("75x6", 75, 6, 2.0, 8.78, 6.89, 46.6, 2.30),
        ("90x7", 90, 7, 2.5, 12.3, 9.64, 95.0, 2.78),
        ("100x8", 100, 8, 2.5, 15.5, 12.2, 145, 3.06),
        ("125x10", 125, 10, 3.0, 24.3, 19.1, 360, 3.85),
    ]

    for a in angles:
        designation, b, t, r_inner, A, mass, Ix, i_x = a
        data = {
            "standard": "GOST 8509-93",
            "type": "angle",
            "designation": designation,
            "b": b,
            "t": t,
            "r": r_inner,
            "mass_per_m": mass,
            "A": A,
            "Ix": Ix,
            "Iy": Ix,
            "i_x": i_x,
            "i_y": i_x, 
        }
        manager.add_profile(data)
    logger.info(f"Added {len(angles)} profiles for GOST 8509-93")

def populate_gost_8240(manager: ProfileManager):
    channels = [
        ("10P", 100, 46, 4.5, 7.6, 8.59, 10.9, 174, 20.4, 34.8, 6.46),
        ("12P", 120, 52, 4.8, 7.8, 10.4, 13.3, 304, 31.2, 50.6, 8.52),
        ("14P", 140, 58, 4.9, 8.1, 12.3, 15.6, 491, 45.4, 70.2, 11.0),
        ("16P", 160, 64, 5.0, 8.4, 14.2, 18.1, 747, 63.3, 93.4, 13.8),
        ("20P", 200, 76, 5.2, 9.0, 18.4, 23.4, 1520, 113, 152, 20.5),
    ]
    
    for c in channels:
        designation, h, b, s, t, mass, A, Ix, Iy, Wx, Wy = c
        data = {
            "standard": "GOST 8240-97",
            "type": "channel",
            "designation": designation,
            "d": h,
            "b": b,
            "t": s,
            "mass_per_m": mass,
            "A": A,
            "Ix": Ix,
            "Iy": Iy,
            "Wx": Wx,
            "Wy": Wy
        }
        manager.add_profile(data)
    logger.info(f"Added {len(channels)} profiles for GOST 8240-97")

def init_database():
    manager = ProfileManager()
    populate_gost_8732(manager)
    populate_gost_8509(manager)
    populate_gost_8240(manager)
    print(f"Database initialized at {manager.db_path}")
    # Create a flag file
    with open("j:/Project/GEO_Vertical/core/db/DB_INIT_DONE", "w") as f:
        f.write("Done")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_database()

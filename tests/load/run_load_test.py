"""
Load Test Runner
================

Script untuk menjalankan load test dengan berbagai skenario.

Usage:
    # Skenario 1: Smoke Test (verifikasi cepat)
    python run_load_test.py --scenario smoke

    # Skenario 2: Load Test (traffic normal)
    python run_load_test.py --scenario load

    # Skenario 3: Stress Test (batas maksimum)
    python run_load_test.py --scenario stress

    # Skenario 4: Spike Test (lonjakan traffic)
    python run_load_test.py --scenario spike

    # Skenario 5: Endurance Test (durasi panjang)
    python run_load_test.py --scenario endurance

    # Custom parameters
    python run_load_test.py --users 50 --duration 10m --host http://localhost:8001

Issue: KOL-42
"""

import subprocess
import sys
import argparse
import os
from datetime import datetime
from pathlib import Path


# Konfigurasi skenario uji
SCENARIOS = {
    "smoke": {
        "description": "Smoke test - verifikasi cepat sistem berfungsi",
        "users": 5,
        "spawn_rate": 5,
        "duration": "1m",
        "tags": None,
        "user_class": "AIEngineUser",
    },
    "load": {
        "description": "Load test - simulasi traffic normal",
        "users": 50,
        "spawn_rate": 10,
        "duration": "5m",
        "tags": None,
        "user_class": "AIEngineUser",
    },
    "stress": {
        "description": "Stress test - mencari batas maksimum",
        "users": 200,
        "spawn_rate": 20,
        "duration": "10m",
        "tags": None,
        "user_class": "AIEngineUser",
    },
    "spike": {
        "description": "Spike test - lonjakan traffic tiba-tiba",
        "users": 100,
        "spawn_rate": 50,  # Spawn cepat untuk spike
        "duration": "3m",
        "tags": None,
        "user_class": "SpikeTestUser",
    },
    "endurance": {
        "description": "Endurance test - tes stabilitas jangka panjang",
        "users": 30,
        "spawn_rate": 5,
        "duration": "30m",
        "tags": None,
        "user_class": "SteadyStateUser",
    },
    "rag_only": {
        "description": "Test RAG endpoint only",
        "users": 50,
        "spawn_rate": 10,
        "duration": "5m",
        "tags": "rag",
        "user_class": "AIEngineUser",
    },
    "health_only": {
        "description": "Test health endpoint only",
        "users": 100,
        "spawn_rate": 20,
        "duration": "2m",
        "tags": "health",
        "user_class": "AIEngineUser",
    },
}


def check_locust_installed():
    """Check if locust is installed."""
    try:
        subprocess.run(["locust", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def install_dependencies():
    """Install required dependencies."""
    print("📦 Installing dependencies...")
    req_file = Path(__file__).parent / "requirements-loadtest.txt"
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(req_file)], check=True
    )
    print("✅ Dependencies installed")


def run_load_test(scenario_config, host, output_dir):
    """Run locust load test with given configuration."""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_prefix = f"{output_dir}/{scenario_config['user_class'].lower()}_{timestamp}"

    cmd = [
        "locust",
        "-f",
        "locustfile.py",
        "--host",
        host,
        "--users",
        str(scenario_config["users"]),
        "--spawn-rate",
        str(scenario_config["spawn_rate"]),
        "--run-time",
        scenario_config["duration"],
        "--headless",
        "--csv",
        csv_prefix,
    ]

    if scenario_config.get("tags"):
        cmd.extend(["--tags", scenario_config["tags"]])

    # Locust user class: use env var (see locust docs). Do not pass class name to -u/--users.
    if (
        scenario_config.get("user_class")
        and scenario_config["user_class"] != "AIEngineUser"
    ):
        import os

        os.environ["LOCUST_USER_CLASSES"] = scenario_config["user_class"]

    print(f"\n{'=' * 70}")
    print(f"🚀 Starting: {scenario_config['description']}")
    print(f"{'=' * 70}")
    print(f"Users: {scenario_config['users']}")
    print(f"Spawn Rate: {scenario_config['spawn_rate']}/s")
    print(f"Duration: {scenario_config['duration']}")
    print(f"Host: {host}")
    print(f"Output: {csv_prefix}")
    print(f"{'=' * 70}\n")

    try:
        subprocess.run(cmd, check=True)
        print(f"\n✅ Test completed successfully")

        # Generate report
        report_file = f"{output_dir}/report_{timestamp}.html"
        report_cmd = [
            sys.executable,
            "generate_report.py",
            "--csv-prefix",
            csv_prefix,
            "--output",
            report_file,
        ]

        print(f"\n📊 Generating report...")
        subprocess.run(report_cmd, check=True)
        print(f"✅ Report saved to: {report_file}")

        return csv_prefix

    except subprocess.CalledProcessError as e:
        print(f"\n❌ Test failed with error code: {e.returncode}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Run AI Engine Load Tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Skenario:
  smoke      - Verifikasi cepat (5 users, 1 menit)
  load       - Traffic normal (50 users, 5 menit)
  stress     - Batas maksimum (200 users, 10 menit)
  spike      - Lonjakan traffic (100 users, 3 menit)
  endurance  - Tes stabilitas (30 users, 30 menit)
  rag_only   - Test RAG endpoint saja
  health_only- Test health endpoint saja

Contoh:
  python run_load_test.py --scenario load
  python run_load_test.py --scenario stress --host http://192.168.1.100:8001
  python run_load_test.py --users 100 --duration 10m --spawn-rate 20
        """,
    )

    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        default="load",
        help="Skenario test (default: load)",
    )
    parser.add_argument(
        "--host",
        default="http://localhost:8001",
        help="Target host (default: http://localhost:8001)",
    )
    parser.add_argument(
        "--output",
        default="./results",
        help="Output directory untuk hasil (default: ./results)",
    )
    parser.add_argument("--users", type=int, help="Override jumlah users")
    parser.add_argument("--duration", help="Override durasi (e.g., 5m, 10m, 1h)")
    parser.add_argument("--spawn-rate", type=int, help="Override spawn rate")
    parser.add_argument(
        "--install", action="store_true", help="Install dependencies terlebih dahulu"
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Install dependencies if requested
    if args.install:
        install_dependencies()

    # Check locust
    if not check_locust_installed():
        print("❌ Locust not installed!")
        print("💡 Run: pip install locust")
        print("   atau: python run_load_test.py --install")
        sys.exit(1)

    # Get scenario config
    scenario_config = SCENARIOS[args.scenario].copy()

    # Override with custom parameters
    if args.users:
        scenario_config["users"] = args.users
    if args.duration:
        scenario_config["duration"] = args.duration
    if args.spawn_rate:
        scenario_config["spawn_rate"] = args.spawn_rate

    # Run test
    result = run_load_test(scenario_config, args.host, str(output_dir))

    if result:
        print(f"\n{'=' * 70}")
        print("✅ Load test selesai!")
        print(f"{'=' * 70}")
        print(f"CSV files: {result}_*.csv")
        print(f"\nUntuk melihat hasil:")
        print(f"  1. Buka report HTML di browser")
        print(f"  2. Atau import CSV ke spreadsheet")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()

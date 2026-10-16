"""Điểm chạy chính.

    python -m newsai.run_all                 # chạy toàn bộ: init-db -> sinh dữ liệu -> ETL -> train -> predict -> forecast
    python -m newsai.run_all --steps etl predict forecast    # chạy định kỳ (không huấn luyện lại)
    python -m newsai.run_all --steps train --force-activate  # huấn luyện lại và bắt buộc kích hoạt
"""
import argparse
import sys
import time

from . import db

ALL_STEPS = ["init-db", "generate", "etl", "train", "predict", "forecast"]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Hệ thống phân tích tin tức tích hợp AI - Phần 1 & 2")
    ap.add_argument("--steps", nargs="+", choices=ALL_STEPS, default=ALL_STEPS)
    ap.add_argument("--force-activate", action="store_true", help="kích hoạt mô hình mới bất kể điểm số")
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # để Windows in được tiếng Việt

    t0 = time.time()
    if "init-db" in args.steps:
        print("== Khởi tạo CSDL trung tâm (schema, view, tài khoản Superset)")
        db.init_db()
    if "generate" in args.steps:
        print("== Sinh dữ liệu giả lập cho hệ thống nguồn")
        from .sample_data import generate
        generate.main()

    conn = db.get_conn()
    try:
        if "etl" in args.steps:
            print("== PHẦN 1: Kết nối nguồn -> CSDL trung tâm")
            from .etl import pipeline
            pipeline.run(conn)
        if "train" in args.steps:
            print("== PHẦN 2: Huấn luyện & đánh giá mô hình AI")
            from .ai import train
            train.train(conn, force_activate=args.force_activate)
        if "predict" in args.steps:
            print("== PHẦN 2: Triển khai mô hình - chấm điểm cảm xúc & từ khóa")
            from .ai import predict
            predict.run(conn)
        if "forecast" in args.steps:
            print("== PHẦN 2: Dự báo chỉ số cảm xúc")
            from .ai import forecast
            forecast.run(conn)
    finally:
        conn.close()
    print(f"== Hoàn tất sau {time.time() - t0:.1f} giây")


if __name__ == "__main__":
    main()

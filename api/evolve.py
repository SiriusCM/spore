"""
进化报告 API。
"""
from flask import Blueprint, jsonify
from database import get_conn

bp = Blueprint("evolve", __name__, url_prefix="/api/evolve")


@bp.route("/reports", methods=["GET"])
def list_reports():
    """获取进化报告列表（最新20条）"""
    try:
        conn = get_conn()
        rows = conn.execute(
            """SELECT id, created_at, state, proposals_count,
                      applied_count, failed_count, snapshot_tag, phase, result_msg
               FROM evolve_reports ORDER BY id DESC LIMIT 20"""
        ).fetchall()
        conn.close()
        reports = [dict(r) for r in rows]
        return jsonify({"success": True, "reports": reports})
    except Exception as e:
        return jsonify({"success": False, "detail": f"List error: {e}"}), 500


@bp.route("/reports/latest", methods=["GET"])
def latest_report():
    """获取最新一条进化报告"""
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM evolve_reports ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        if not row:
            return jsonify({"success": True, "report": None})
        return jsonify({"success": True, "report": dict(row)})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Get error: {e}"}), 500


@bp.route("/reports/<int:report_id>", methods=["GET"])
def get_report(report_id):
    """获取指定报告的完整内容"""
    try:
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM evolve_reports WHERE id = ?", (report_id,)
        ).fetchone()
        conn.close()
        if not row:
            return jsonify({"success": False, "detail": "报告不存在"}), 404
        return jsonify({"success": True, "report": dict(row)})
    except Exception as e:
        return jsonify({"success": False, "detail": f"Get error: {e}"}), 500
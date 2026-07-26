"""
Corpus AI - Dashboard Router
============================
Endpoints for generating tenant-level metrics, usage graphs, and popular queries list.
Restricted to Company Administrators.
"""

import logging
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.auth import require_role
from app.db import get_db
from app.models import Document, QueryLog, User, utc_now
from app.schemas import (
    DashboardPopularResponse,
    DashboardStats,
    DashboardUsageResponse,
    PopularQuery,
    UsageDataPoint,
)

logger = logging.getLogger("corpus_ai.dashboard_router")

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get(
    "/stats",
    response_model=DashboardStats,
    summary="Get tenant statistics dashboard (admin only)",
)
def get_stats(
    current_user: User = Depends(require_role("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Aggregates system usage telemetry statistics for the administrator's company workspace.
    
    Filters all counts and averages to guarantee strict data separation.
    """
    try:
        company_id = current_user.company_id

        # 1. Total Documents count
        total_docs = db.query(Document).filter(Document.company_id == company_id).count()

        # 2. Total Queries processed
        total_queries = db.query(QueryLog).filter(QueryLog.company_id == company_id).count()

        # 3. Active Users count (Total users currently active in company)
        active_users = db.query(User).filter(
            User.company_id == company_id,
            User.is_active == True
        ).count()

        # 4. Total Chunks indexed (Sum of chunk_count in Documents table)
        total_chunks = db.query(func.sum(Document.chunk_count)).filter(
            Document.company_id == company_id
        ).scalar() or 0

        # 5. Average response latency
        avg_latency = db.query(func.avg(QueryLog.latency_ms)).filter(
            QueryLog.company_id == company_id
        ).scalar() or 0.0

        # 6. Cache hit ratio
        cache_hits = db.query(QueryLog).filter(
            QueryLog.company_id == company_id,
            QueryLog.cache_hit == True
        ).count()
        
        cache_hit_ratio = float(cache_hits) / float(total_queries) if total_queries > 0 else 0.0

        return DashboardStats(
            total_documents=total_docs,
            total_queries=total_queries,
            active_users=active_users,
            total_chunks=int(total_chunks),
            avg_latency_ms=float(round(avg_latency, 2)),
            cache_hit_ratio=float(round(cache_hit_ratio, 4))
        )

    except Exception as e:
        logger.error("Failed to generate dashboard statistics: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compute dashboard metrics logs",
        )


@router.get(
    "/popular",
    response_model=DashboardPopularResponse,
    summary="Get top queries asked in the workspace (admin only)",
)
def get_popular_queries(
    current_user: User = Depends(require_role("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Retrieve the most frequent inquiries asked by users in this tenant company workspace."""
    try:
        company_id = current_user.company_id

        # Query top 5 questions, group by lowercased text representation
        popular = db.query(
            func.lower(QueryLog.question).label("q_text"),
            func.count(QueryLog.id).label("q_count")
        ).filter(
            QueryLog.company_id == company_id
        ).group_by(
            text("q_text")
        ).order_by(
            text("q_count DESC")
        ).limit(5).all()

        queries_list = []
        for row in popular:
            # Capitalize first letter of question to look nice in UI
            raw_q = row[0]
            display_q = raw_q[0].upper() + raw_q[1:] if raw_q else ""
            queries_list.append(
                PopularQuery(
                    question=display_q,
                    count=row[1]
                )
            )

        return DashboardPopularResponse(queries=queries_list)

    except Exception as e:
        logger.error("Failed to query popular queries log: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query database telemetry logs",
        )


@router.get(
    "/usage",
    response_model=DashboardUsageResponse,
    summary="Get daily query counts over the past 30 days (admin only)",
)
def get_usage_over_time(
    current_user: User = Depends(require_role("admin", "super_admin")),
    db: Session = Depends(get_db),
):
    """Aggregates queries count grouped daily for the past 30 days."""
    try:
        company_id = current_user.company_id
        thirty_days_ago = utc_now() - timedelta(days=30)

        # In SQLite, we parse using strftime('%Y-%m-%d', created_at)
        # In PostgreSQL, we parse using date_trunc('day', created_at)
        # We branch here or use SQL standard constructs.
        # Since SQLite is dev, we can write a database-agnostic or clean format check.
        # Let's write standard strftime filter if settings.is_sqlite, otherwise date_trunc/to_char
        from app.config import settings
        
        if settings.is_sqlite:
            date_field = func.strftime("%Y-%m-%d", QueryLog.created_at)
        else:
            date_field = func.to_char(QueryLog.created_at, "YYYY-MM-DD")

        usage = db.query(
            date_field.label("day"),
            func.count(QueryLog.id).label("queries_count")
        ).filter(
            QueryLog.company_id == company_id,
            QueryLog.created_at >= thirty_days_ago
        ).group_by(
            text("day")
        ).order_by(
            text("day ASC")
        ).all()

        # Build usage dictionary to populate empty days
        usage_dict = {row[0]: row[1] for row in usage if row[0] is not None}

        # Ensure all 30 days are present in the list for clean UI charts
        data_points = []
        for i in range(30):
            day_dt = utc_now() - timedelta(days=30 - i)
            day_str = day_dt.strftime("%Y-%m-%d")
            count = usage_dict.get(day_str, 0)
            data_points.append(
                UsageDataPoint(
                    date=day_str,
                    query_count=count
                )
            )

        return DashboardUsageResponse(data=data_points, period_days=30)

    except Exception as e:
        logger.error("Failed to compile usage analytics graph: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compile daily request frequency logs",
        )

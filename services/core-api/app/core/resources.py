from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
)
redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def check_redis() -> None:
    if not await redis_client.ping():
        raise RuntimeError("Redis ping failed")


async def ensure_audit_table() -> None:
    statement = text(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id BIGSERIAL PRIMARY KEY,
            occurred_at TIMESTAMPTZ NOT NULL,
            request_id VARCHAR(128) NOT NULL,
            actor TEXT,
            tenant_id UUID,
            method VARCHAR(16) NOT NULL,
            path TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            action TEXT NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )

    async with engine.begin() as connection:
        await connection.execute(statement)


async def write_audit_event(event: dict[str, object]) -> None:
    import json

    tenant_id = event.get("tenant_id")
    actor = event.get("actor")

    if not tenant_id or not actor:
        return

    status_code = int(event.get("status_code", 500))

    if status_code < 400:
        decision = "allowed"
    elif status_code < 500:
        decision = "denied"
    else:
        decision = "error"

    statement = text(
        """
        INSERT INTO audit_events (
            tenant_id,
            actor_subject,
            action,
            resource_type,
            resource_id,
            decision,
            request_id,
            data
        )
        VALUES (
            CAST(:tenant_id AS UUID),
            :actor_subject,
            :action,
            :resource_type,
            :resource_id,
            :decision,
            :request_id,
            CAST(:data AS JSONB)
        )
        """
    )

    data = {
        "method": event.get("method"),
        "path": event.get("path"),
        "status_code": status_code,
        "occurred_at": event.get("occurred_at"),
        "metadata": event.get("metadata", {}),
    }

    values = {
        "tenant_id": str(tenant_id),
        "actor_subject": str(actor),
        "action": str(event.get("action", "unknown")),
        "resource_type": "http_request",
        "resource_id": None,
        "decision": decision,
        "request_id": str(event.get("request_id", "")),
        "data": json.dumps(data, ensure_ascii=False),
    }

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": str(tenant_id)},
        )
        await connection.execute(statement, values)


async def list_audit_events(
    *,
    tenant_id: str,
    limit: int = 50,
    actor: str | None = None,
    decision: str | None = None,
    action: str | None = None,
) -> list[dict[str, object]]:
    values: dict[str, object] = {
        "tenant_id": tenant_id,
        "limit": limit,
        "actor": actor or None,
        "decision": decision or None,
        "action": action or None,
    }

    statement = text(
        """
        SELECT
            id,
            tenant_id,
            actor_subject,
            action,
            resource_type,
            resource_id,
            decision,
            request_id,
            data,
            created_at
        FROM audit_events
        WHERE tenant_id = CAST(:tenant_id AS UUID)
          AND (
              CAST(:actor AS TEXT) IS NULL
              OR actor_subject = CAST(:actor AS TEXT)
          )
          AND (
              CAST(:decision AS TEXT) IS NULL
              OR decision = CAST(:decision AS TEXT)
          )
          AND (
              CAST(:action AS TEXT) IS NULL
              OR action = CAST(:action AS TEXT)
          )
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": tenant_id},
        )

        result = await connection.execute(statement, values)

        return [
            {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "actor": row.actor_subject,
                "action": row.action,
                "resource_type": row.resource_type,
                "resource_id": row.resource_id,
                "decision": row.decision,
                "request_id": row.request_id,
                "data": row.data,
                "created_at": row.created_at.isoformat(),
            }
            for row in result
        ]


async def resolve_principal_access(
    *,
    tenant_id: str,
    subject: str,
) -> dict[str, object] | None:
    statement = text(
        """
        SELECT
            t.status AS tenant_status,
            m.id AS membership_id,
            m.status AS membership_status,
            COALESCE(
                access.roles,
                ARRAY[]::varchar[]
            ) AS roles,
            COALESCE(
                access.permission_assignments,
                '[]'::jsonb
            ) AS permission_assignments
        FROM tenants AS t
        LEFT JOIN memberships AS m
            ON m.tenant_id = t.id
           AND m.external_subject = :subject
        LEFT JOIN LATERAL (
            SELECT
                COALESCE(
                    array_agg(DISTINCT r.key)
                        FILTER (WHERE r.key IS NOT NULL),
                    ARRAY[]::varchar[]
                ) AS roles,
                COALESCE(
                    jsonb_agg(
                        DISTINCT jsonb_build_object(
                            'key',
                            rp.permission_key,
                            'role_key',
                            r.key,
                            'scope',
                            rp.scope
                        )
                    ) FILTER (
                        WHERE rp.permission_key IS NOT NULL
                    ),
                    '[]'::jsonb
                ) AS permission_assignments
            FROM membership_roles AS mr
            JOIN roles AS r
              ON r.tenant_id = mr.tenant_id
             AND r.id = mr.role_id
            LEFT JOIN role_permissions AS rp
              ON rp.tenant_id = r.tenant_id
             AND rp.role_id = r.id
            WHERE mr.tenant_id = m.tenant_id
              AND mr.membership_id = m.id
        ) AS access ON m.id IS NOT NULL
        WHERE t.id = CAST(:tenant_id AS UUID)
        """
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": tenant_id},
        )

        result = await connection.execute(
            statement,
            {
                "tenant_id": tenant_id,
                "subject": subject,
            },
        )
        row = result.mappings().first()

    if row is None:
        return None

    return {
        "tenant_status": row["tenant_status"],
        "membership_id": (
            str(row["membership_id"])
            if row["membership_id"] is not None
            else None
        ),
        "membership_status": row["membership_status"],
        "roles": tuple(row["roles"] or ()),
        "permission_assignments": tuple(
            row["permission_assignments"] or ()
        ),
    }


async def resolve_membership_access(
    *,
    tenant_id: str,
    membership_id: str,
) -> dict[str, object] | None:
    """Resolve authorization using only OPEX tenant and membership IDs."""
    statement = text(
        """
        SELECT
            t.status AS tenant_status,
            m.id AS membership_id,
            m.status AS membership_status,
            COALESCE(
                access.roles,
                ARRAY[]::varchar[]
            ) AS roles,
            COALESCE(
                access.permission_assignments,
                '[]'::jsonb
            ) AS permission_assignments
        FROM tenants AS t
        LEFT JOIN memberships AS m
            ON m.tenant_id = t.id
           AND m.id = CAST(:membership_id AS UUID)
        LEFT JOIN LATERAL (
            SELECT
                COALESCE(
                    array_agg(DISTINCT r.key)
                        FILTER (
                            WHERE r.key IS NOT NULL
                        ),
                    ARRAY[]::varchar[]
                ) AS roles,
                COALESCE(
                    jsonb_agg(
                        DISTINCT jsonb_build_object(
                            'key',
                            rp.permission_key,
                            'role_key',
                            r.key,
                            'scope',
                            rp.scope
                        )
                    ) FILTER (
                        WHERE rp.permission_key IS NOT NULL
                    ),
                    '[]'::jsonb
                ) AS permission_assignments
            FROM membership_roles AS mr
            JOIN roles AS r
              ON r.tenant_id = mr.tenant_id
             AND r.id = mr.role_id
            LEFT JOIN role_permissions AS rp
              ON rp.tenant_id = r.tenant_id
             AND rp.role_id = r.id
            WHERE mr.tenant_id = m.tenant_id
              AND mr.membership_id = m.id
        ) AS access
            ON m.id IS NOT NULL
        WHERE t.id = CAST(:tenant_id AS UUID)
        """
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {
                "tenant_id": tenant_id,
            },
        )

        result = await connection.execute(
            statement,
            {
                "tenant_id": tenant_id,
                "membership_id": membership_id,
            },
        )

        row = result.mappings().first()

    if row is None:
        return None

    return {
        "tenant_status": row["tenant_status"],
        "membership_id": (
            str(row["membership_id"])
            if row["membership_id"] is not None
            else None
        ),
        "membership_status": row["membership_status"],
        "roles": tuple(
            row["roles"] or ()
        ),
        "permission_assignments": tuple(
            row["permission_assignments"] or ()
        ),
    }


async def resolve_external_identity_membership(
    *,
    tenant_id: str,
    provider_id: str,
    subject: str,
) -> str | None:
    """Map a verified external identity to an internal membership ID."""
    statement = text(
        """
        SELECT
            ei.membership_id
        FROM external_identities AS ei
        JOIN identity_providers AS ip
          ON ip.tenant_id = ei.tenant_id
         AND ip.id = ei.provider_id
        WHERE ei.tenant_id = CAST(:tenant_id AS UUID)
          AND ei.provider_id = CAST(:provider_id AS UUID)
          AND ei.subject = :subject
          AND ei.status = 'active'
          AND ip.status = 'active'
        """
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {
                "tenant_id": tenant_id,
            },
        )

        membership_id = await connection.scalar(
            statement,
            {
                "tenant_id": tenant_id,
                "provider_id": provider_id,
                "subject": subject,
            },
        )

    return (
        str(membership_id)
        if membership_id is not None
        else None
    )


async def update_tenant_display_name(
    *,
    tenant_id: str,
    display_name: str,
) -> dict[str, object] | None:
    statement = text(
        """
        UPDATE tenants
        SET
            display_name = :display_name,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = CAST(:tenant_id AS UUID)
        RETURNING
            id,
            slug,
            display_name,
            status,
            created_at,
            updated_at
        """
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": tenant_id},
        )

        result = await connection.execute(
            statement,
            {
                "tenant_id": tenant_id,
                "display_name": display_name,
            },
        )
        row = result.mappings().first()

    if row is None:
        return None

    return {
        "id": str(row["id"]),
        "slug": row["slug"],
        "display_name": row["display_name"],
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


async def get_tenant(
    *,
    tenant_id: str,
) -> dict[str, object] | None:
    statement = text(
        """
        SELECT
            id,
            slug,
            display_name,
            status,
            created_at,
            updated_at
        FROM tenants
        WHERE id = CAST(:tenant_id AS UUID)
        """
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": tenant_id},
        )

        result = await connection.execute(
            statement,
            {"tenant_id": tenant_id},
        )
        row = result.mappings().first()

    if row is None:
        return None

    return {
        "id": str(row["id"]),
        "slug": row["slug"],
        "display_name": row["display_name"],
        "status": row["status"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


async def list_tenant_roles(
    *,
    tenant_id: str,
) -> list[dict[str, object]]:
    statement = text(
        """
        SELECT
            id,
            key,
            name,
            is_system,
            created_at
        FROM roles
        WHERE tenant_id = CAST(:tenant_id AS UUID)
        ORDER BY key ASC
        """
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": tenant_id},
        )

        result = await connection.execute(
            statement,
            {"tenant_id": tenant_id},
        )

        return [
            {
                "id": str(row["id"]),
                "key": row["key"],
                "name": row["name"],
                "is_system": row["is_system"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in result.mappings()
        ]


async def create_tenant_member(
    *,
    tenant_id: str,
    subject: str,
    email: str | None,
    display_name: str | None,
    roles: tuple[str, ...],
) -> dict[str, object]:
    requested_roles = tuple(
        sorted(
            {
                role.strip().lower()
                for role in roles
                if role.strip()
            }
        )
    )

    if not requested_roles:
        raise ValueError("At least one role is required")

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": tenant_id},
        )

        role_result = await connection.execute(
            text(
                """
                SELECT id, key
                FROM roles
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND is_system = true
                  AND key = ANY(CAST(:roles AS varchar[]))
                """
            ),
            {
                "tenant_id": tenant_id,
                "roles": list(requested_roles),
            },
        )

        role_rows = role_result.mappings().all()
        resolved_roles = {
            row["key"]: row["id"]
            for row in role_rows
        }

        missing_roles = sorted(
            set(requested_roles) - set(resolved_roles)
        )

        if missing_roles:
            raise ValueError(
                "Unknown or non-system roles: "
                + ", ".join(missing_roles)
            )

        membership_id = await connection.scalar(
            text(
                """
                INSERT INTO memberships (
                    tenant_id,
                    external_subject,
                    email,
                    display_name,
                    status
                )
                VALUES (
                    CAST(:tenant_id AS UUID),
                    :subject,
                    :email,
                    :display_name,
                    'active'
                )
                ON CONFLICT (tenant_id, external_subject)
                DO NOTHING
                RETURNING id
                """
            ),
            {
                "tenant_id": tenant_id,
                "subject": subject,
                "email": email,
                "display_name": display_name,
            },
        )

        if membership_id is None:
            raise ValueError(
                "Membership already exists for this subject"
            )

        for role_key in requested_roles:
            await connection.execute(
                text(
                    """
                    INSERT INTO membership_roles (
                        tenant_id,
                        membership_id,
                        role_id
                    )
                    VALUES (
                        CAST(:tenant_id AS UUID),
                        CAST(:membership_id AS UUID),
                        CAST(:role_id AS UUID)
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "membership_id": str(membership_id),
                    "role_id": str(resolved_roles[role_key]),
                },
            )

    return {
        "id": str(membership_id),
        "subject": subject,
        "email": email,
        "display_name": display_name,
        "status": "active",
        "roles": list(requested_roles),
    }


async def update_tenant_member_access(
    *,
    tenant_id: str,
    membership_id: str,
    membership_status: str,
    roles: tuple[str, ...],
) -> dict[str, object]:
    requested_status = membership_status.strip().lower()

    if requested_status not in {"active", "suspended"}:
        raise ValueError("Membership status must be active or suspended")

    requested_roles = tuple(
        sorted(
            {
                role.strip().lower()
                for role in roles
                if role.strip()
            }
        )
    )

    if not requested_roles:
        raise ValueError("At least one role is required")

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": tenant_id},
        )

        # Serialize access-control changes inside the same tenant so two
        # concurrent requests cannot both remove the final super admin.
        await connection.execute(
            text(
                """
                SELECT pg_advisory_xact_lock(
                    hashtextextended(:tenant_id, 0)
                )
                """
            ),
            {"tenant_id": tenant_id},
        )

        membership = (
            await connection.execute(
                text(
                    """
                    SELECT
                        id,
                        external_subject,
                        email,
                        display_name,
                        status
                    FROM memberships
                    WHERE tenant_id = CAST(:tenant_id AS UUID)
                      AND id = CAST(:membership_id AS UUID)
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "membership_id": membership_id,
                },
            )
        ).mappings().first()

        if membership is None:
            raise ValueError("Membership not found")

        role_result = await connection.execute(
            text(
                """
                SELECT id, key
                FROM roles
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND is_system = true
                  AND key = ANY(CAST(:roles AS varchar[]))
                """
            ),
            {
                "tenant_id": tenant_id,
                "roles": list(requested_roles),
            },
        )

        resolved_roles = {
            row["key"]: row["id"]
            for row in role_result.mappings()
        }

        missing_roles = sorted(
            set(requested_roles) - set(resolved_roles)
        )

        if missing_roles:
            raise ValueError(
                "Unknown or non-system roles: "
                + ", ".join(missing_roles)
            )

        currently_super_admin = bool(
            await connection.scalar(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM membership_roles AS mr
                        JOIN roles AS r
                          ON r.tenant_id = mr.tenant_id
                         AND r.id = mr.role_id
                        WHERE mr.tenant_id = CAST(:tenant_id AS UUID)
                          AND mr.membership_id = CAST(:membership_id AS UUID)
                          AND r.key = 'super_admin'
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "membership_id": membership_id,
                },
            )
        )

        removes_active_super_admin = (
            membership["status"] == "active"
            and currently_super_admin
            and (
                requested_status != "active"
                or "super_admin" not in requested_roles
            )
        )

        if removes_active_super_admin:
            other_active_super_admins = int(
                await connection.scalar(
                    text(
                        """
                        SELECT COUNT(DISTINCT m.id)
                        FROM memberships AS m
                        JOIN membership_roles AS mr
                          ON mr.tenant_id = m.tenant_id
                         AND mr.membership_id = m.id
                        JOIN roles AS r
                          ON r.tenant_id = mr.tenant_id
                         AND r.id = mr.role_id
                        WHERE m.tenant_id = CAST(:tenant_id AS UUID)
                          AND m.id <> CAST(:membership_id AS UUID)
                          AND m.status = 'active'
                          AND r.key = 'super_admin'
                        """
                    ),
                    {
                        "tenant_id": tenant_id,
                        "membership_id": membership_id,
                    },
                )
                or 0
            )

            if other_active_super_admins == 0:
                raise ValueError(
                    "Cannot remove or suspend the last active super admin"
                )

        await connection.execute(
            text(
                """
                UPDATE memberships
                SET
                    status = :membership_status,
                    updated_at = CURRENT_TIMESTAMP
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND id = CAST(:membership_id AS UUID)
                """
            ),
            {
                "tenant_id": tenant_id,
                "membership_id": membership_id,
                "membership_status": requested_status,
            },
        )

        await connection.execute(
            text(
                """
                DELETE FROM membership_roles
                WHERE tenant_id = CAST(:tenant_id AS UUID)
                  AND membership_id = CAST(:membership_id AS UUID)
                """
            ),
            {
                "tenant_id": tenant_id,
                "membership_id": membership_id,
            },
        )

        for role_key in requested_roles:
            await connection.execute(
                text(
                    """
                    INSERT INTO membership_roles (
                        tenant_id,
                        membership_id,
                        role_id
                    )
                    VALUES (
                        CAST(:tenant_id AS UUID),
                        CAST(:membership_id AS UUID),
                        CAST(:role_id AS UUID)
                    )
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "membership_id": membership_id,
                    "role_id": str(resolved_roles[role_key]),
                },
            )

    return {
        "id": str(membership["id"]),
        "subject": membership["external_subject"],
        "email": membership["email"],
        "display_name": membership["display_name"],
        "status": requested_status,
        "roles": list(requested_roles),
    }


async def list_tenant_members(
    *,
    tenant_id: str,
) -> list[dict[str, object]]:
    statement = text(
        """
        SELECT
            m.id,
            m.external_subject,
            m.email,
            m.display_name,
            m.status,
            m.created_at,
            m.updated_at,
            COALESCE(
                array_agg(r.key ORDER BY r.key)
                    FILTER (WHERE r.key IS NOT NULL),
                ARRAY[]::varchar[]
            ) AS roles
        FROM memberships AS m
        LEFT JOIN membership_roles AS mr
            ON mr.tenant_id = m.tenant_id
           AND mr.membership_id = m.id
        LEFT JOIN roles AS r
            ON r.tenant_id = mr.tenant_id
           AND r.id = mr.role_id
        WHERE m.tenant_id = CAST(:tenant_id AS UUID)
        GROUP BY
            m.id,
            m.external_subject,
            m.email,
            m.display_name,
            m.status,
            m.created_at,
            m.updated_at
        ORDER BY m.created_at ASC, m.external_subject ASC
        """
    )

    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                SELECT set_config(
                    'app.tenant_id',
                    :tenant_id,
                    true
                )
                """
            ),
            {"tenant_id": tenant_id},
        )

        result = await connection.execute(
            statement,
            {"tenant_id": tenant_id},
        )

        return [
            {
                "id": str(row["id"]),
                "subject": row["external_subject"],
                "email": row["email"],
                "display_name": row["display_name"],
                "status": row["status"],
                "roles": list(row["roles"] or ()),
                "created_at": row["created_at"].isoformat(),
                "updated_at": (
                    row["updated_at"].isoformat()
                    if row["updated_at"] is not None
                    else None
                ),
            }
            for row in result.mappings()
        ]


async def close_resources() -> None:
    await redis_client.aclose()
    await engine.dispose()


PREAUTH_PROVIDER_SAFE_FIELDS = (
    "tenant_id",
    "tenant_slug",
    "provider_id",
    "provider_key",
    "protocol",
    "provider_display_name",
    "issuer",
    "client_id",
    "audiences",
    "scopes",
    "allowed_algorithms",
)


def _require_canonical_preauth_hostname(
    hostname: str,
) -> str:
    if not isinstance(hostname, str):
        raise ValueError(
            "Pre-auth hostname is invalid"
        )

    if (
        not hostname
        or len(hostname) > 253
        or hostname != hostname.strip()
        or hostname != hostname.lower()
        or hostname.startswith(".")
        or hostname.endswith(".")
        or ".." in hostname
    ):
        raise ValueError(
            "Pre-auth hostname is invalid"
        )

    try:
        hostname.encode(
            "ascii",
            errors="strict",
        )
    except UnicodeEncodeError as exc:
        raise ValueError(
            "Pre-auth hostname is invalid"
        ) from exc

    if any(
        not (
            character.isdigit()
            or "a" <= character <= "z"
            or character in ".-"
        )
        for character in hostname
    ):
        raise ValueError(
            "Pre-auth hostname is invalid"
        )

    return hostname


async def resolve_preauth_oidc_providers(
    *,
    hostname: str,
) -> tuple[dict[str, object], ...]:
    """
    Resolve safe OIDC bootstrap metadata for a canonical hostname.

    Tenant resolution deliberately goes through the hardened
    SECURITY DEFINER database function. Core runtime does not
    receive direct pre-auth table access.
    """

    canonical_hostname = (
        _require_canonical_preauth_hostname(
            hostname
        )
    )

    statement = text(
        """
        SELECT
            tenant_id,
            tenant_slug,
            provider_id,
            provider_key,
            protocol,
            provider_display_name,
            issuer,
            client_id,
            audiences,
            scopes,
            allowed_algorithms
        FROM public.resolve_preauth_oidc_providers(
            :hostname
        )
        """
    )

    async with engine.connect() as connection:
        result = await connection.execute(
            statement,
            {
                "hostname":
                    canonical_hostname,
            },
        )

        rows = result.mappings().all()

    providers = []

    for row in rows:
        item = {
            field: row[field]
            for field
            in PREAUTH_PROVIDER_SAFE_FIELDS
        }

        # Convert UUID-like values at the resource boundary so
        # callers receive a stable serialization-safe contract.
        item["tenant_id"] = str(
            item["tenant_id"]
        )

        item["provider_id"] = str(
            item["provider_id"]
        )

        item["audiences"] = tuple(
            item["audiences"] or ()
        )

        item["scopes"] = tuple(
            item["scopes"] or ()
        )

        item["allowed_algorithms"] = tuple(
            item["allowed_algorithms"] or ()
        )

        providers.append(
            item
        )

    return tuple(
        providers
    )

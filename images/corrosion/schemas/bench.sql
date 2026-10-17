-- Benchmark schema (E1-E6). Corrosion requires a non-null primary key; other columns are nullable.
CREATE TABLE resources (
    id TEXT NOT NULL PRIMARY KEY,
    region TEXT,
    status TEXT,
    cpu_capacity INTEGER,
    memory_capacity INTEGER,
    version INTEGER,
    doc TEXT
);

CREATE TABLE allocations (
    id TEXT NOT NULL PRIMARY KEY,
    resource_id TEXT,
    app TEXT
);

-- Secondary indexes on the fields OptimusDB indexes by default (type, status, region, resource_id), so that
-- neither system has an index advantage in E3 (resources has no `type` column; allocations are a table here).
CREATE INDEX resources_status ON resources (status);
CREATE INDEX resources_region ON resources (region);
CREATE INDEX allocations_resource_id ON allocations (resource_id);

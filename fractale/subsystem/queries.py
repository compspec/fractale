# A cluster has one or more subsystems
create_clusters_sql = """
CREATE TABLE clusters (
  name TEXT PRIMARY KEY NOT NULL
);"""

# A subsystem is owned by a cluster, and has nodes and edges
# We store the type here (defined at the root) for easy query
create_subsystem_sql = """
CREATE TABLE subsystems (
  name TEXT NOT NULL,
  cluster TEXT NOT NULL,
  type TEXT NOT NULL,
  PRIMARY KEY (name, cluster)
);"""

create_nodes_sql = """CREATE TABLE nodes (
  table_id INTEGER PRIMARY KEY,
  subsystem TEXT NOT NULL,
  cluster TEXT NOT NULL,
  label TEXT NOT NULL,
  type TEXT NOT NULL,
  basename TEXT NOT NULL,
  name TEXT NOT NULL,
  id INTEGER NOT NULL,
  FOREIGN KEY(subsystem, cluster) REFERENCES subsystems(name, cluster),
  UNIQUE (cluster, subsystem, label)
);"""

create_attributes_sql = """CREATE TABLE attributes (
  name TEXT NOT NULL,
  subsystem TEXT NOT NULL,
  cluster TEXT NOT NULL,
  value TEXT NOT NULL,
  node TEXT NOT NULL,
  FOREIGN KEY(node) REFERENCES nodes(table_id)
);"""

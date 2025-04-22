import os
import sqlite3

import fractale.subsystem.queries as queries
from fractale.logger import LogColors, logger

from .base import Solver


class DatabaseSolver(Solver):
    """
    A database solver solves for a cluster based on a simple database.
    """

    def __init__(self, path):
        self.subsystems = {}
        self.conn = sqlite3.connect(":memory:")
        self.create_tables()
        self.load(path)

    def __exit__(self):
        self.close()

    def close(self):
        self.conn.close()

    def create_tables(self):
        """
        Create tables for subsytems, nodes, edges.

        Note that I'm flattening the graph, so edges become attributes for
        nodes so it's easy to query. This is a reasonable first shot over
        implementing an actual graph database.
        """
        cursor = self.conn.cursor()

        # Only save metadata we absolutely need
        # Note I'm not saving edges because we don't use
        # them for anything - we are going to parse them
        # into node attributes instead.
        create_sql = [
            queries.create_subsystem_sql,
            queries.create_clusters_sql,
            queries.create_nodes_sql,
            queries.create_attributes_sql,
        ]
        for sql in create_sql:
            cursor.execute(sql)
        self.conn.commit()

    def load_subsystem(self, subsystem):
        """
        Load a new subsystem to the memory database
        """
        cursor = self.conn.cursor()

        # Create the cluster if it doesn't exist
        values = f"('{subsystem.cluster}')"
        fields = '("name")'
        statement = f"INSERT OR IGNORE INTO clusters {fields} VALUES {values}"
        logger.debug(statement)
        cursor.execute(statement)
        self.conn.commit()

        # Create the subsystem - it should error if already exists
        values = f"('{subsystem.name}', '{subsystem.cluster}', '{subsystem.type}')"
        fields = '("name", "cluster", "type")'
        statement = f"INSERT INTO subsystems {fields} VALUES {values}"
        logger.debug(statement)
        cursor.execute(statement)
        self.conn.commit()

        # These are fields to insert a node and attributes
        node_fields = '("subsystem", "cluster", "label", "type", "basename", "name", "id")'

        # NOTE: we don't create nodes here, e.g., iterate and parse into nodes table
        # This would be subsystem.name, cluster name, nid, type basename, name
        # Instead we just add attributes
        attr_fields = '("cluster", "subsystem", "node", "name", "value")'

        # Keep track of counts of all types
        counts = {}

        # Now all attributes, and also include type because I'm lazy
        for nid, node in subsystem.iter_nodes():
            typ = node["metadata"]["type"]

            # Assume a node is a count of 1
            if typ not in counts:
                counts[typ] = 0
            counts[typ] += 1

            attr_values = f"('{subsystem.cluster}', '{subsystem.name}', '{nid}', 'type', '{typ}')"
            statement = f"INSERT INTO attributes {attr_fields} VALUES {attr_values}"
            cursor.execute(statement)
            for key, value in node["metadata"].get("attributes", {}).items():
                attr_values = (
                    f"('{subsystem.cluster}', '{subsystem.name}', '{nid}', '{key}', '{value}')"
                )
                statement = f"INSERT INTO attributes {attr_fields} VALUES {attr_values}"
                cursor.execute(statement)

        # Note that we aren't doing anything with edges currently.
        self.conn.commit()
        self.subsystems[subsystem.name] = counts

    def get_subsystem_nodes(self, cluster, subsystem):
        """
        Get nodes of a subsystem and cluster

        Technically we could skip labels, but I'm assuming we eventually want
        nodes in this query somewhere.
        """
        statement = (
            f"SELECT label from nodes WHERE subsystem = '{subsystem}' AND cluster = '{cluster}';"
        )
        labels = self.query(statement)
        return [f"'{x[0]}'" for x in labels]

    def render(self, subsystems):
        """
        Yield lines for the transformer.
        """
        for subsystem, items in subsystems.items():
            for item in items:
                # This is actually easier to do than a query!
                if subsystem == "spack":
                    for require in item.requires:
                        item_type = require.get("type")
                        item_name = require.get("name")
                        if item_type == "binary" and item_name is not None:
                            yield f"\nspack load {item_name}"

                        elif subsystem == "environment-modules":
                            item_type = require.get("type")
                            # TODO we need to test if this will with with <.>
                            item_name = require.get("attribute.name")
                            if item_type == "module" and item_name is not None:
                                yield f"\nmodule load {item_name}"

    def find_nodes(self, cluster, name, items):
        """
        Given a list of node labels, find children (attributes)
        that have a specific key/value.
        """
        # Final nodes that satisfy all item requirements
        satisfy = set()

        # Each item is a set of requirements for one NODE. If we cannot satisfy one software
        # requirement the cluster does not match.
        for item in items:
            nodes = set()
            i = 0
            for key, value in item.items():
                statement = f"SELECT * from attributes WHERE cluster = '{cluster}' AND subsystem = '{name}' AND name = '{key}' AND value like '{value}';"
                result = self.query(statement)
                # We don't have any nodes yet, all are contenders
                if i == 0:
                    [nodes.add(x[-1]) for x in result]
                else:
                    new_nodes = {x[-1] for x in result}
                    nodes = nodes.intersection(new_nodes)
                i += 1

                # If we don't have nodes left, the cluster isn't a match
                if not nodes:
                    return

            # If we get down here, we found a matching node for one item requirement
            [satisfy.add(x) for x in nodes]
        return satisfy

    def query(self, statement):
        """
        Issue a query to the database, returning fetchall.
        """
        cursor = self.conn.cursor()
        printed = statement

        # Don't overwhelm the output!
        if len(printed) > 150:
            printed = printed[:150] + "..."
        printed = f"{LogColors.OKCYAN}{printed}{LogColors.ENDC}"
        cursor.execute(statement)
        self.conn.commit()

        # Get results, show query and number of results
        results = cursor.fetchall()
        count = (f"{LogColors.PURPLE}({len(results)}){LogColors.ENDC} ").rjust(20)
        logger.info(count + printed)
        return results

    def assess_containment(self, requires):
        """
        A rough heuirstic to see if the cluster has enough resources
        of specific types.
        """
        for typ, count in requires.items():
            if typ not in self.subsystems.get("containment", {}):
                return False
            have_count = self.subsystems["containment"][typ]
            if have_count < count:
                return False
        return True

    def get_subsystem_by_type(self, subsystem_type, ignore_missing=True):
        """
        Get subsystems based on a type. This will return one or more clusters
        that will be contenders for matching.
        """
        # Check 2: the subsystem exists in our database
        statement = f"SELECT * from subsystems WHERE type = '{subsystem_type}';"
        return self.query(statement)

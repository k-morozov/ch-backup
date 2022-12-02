"""
Clickhouse backup logic for databases
"""
from typing import Sequence

from ch_backup import logging
from ch_backup.backup.layout import BackupLayout
from ch_backup.backup.metadata import BackupMetadata
from ch_backup.clickhouse.control import ClickhouseCTL
from ch_backup.clickhouse.schema import rewrite_database_schema
from ch_backup.config import Config
from ch_backup.logic.backup_manager import BackupManager
from ch_backup.util import get_database_zookeeper_paths
from ch_backup.zookeeper.zookeeper import ZookeeperCTL


class DatabaseBackup(BackupManager):
    """
    Database backup class
    """
    def __init__(self, ch_ctl: ClickhouseCTL, backup_layout: BackupLayout, config: Config) -> None:
        super().__init__(ch_ctl, backup_layout)
        self._config = config['backup']
        self._zk_config = config.get('zookeeper')

    def backup(self, backup_meta: BackupMetadata, databases: Sequence[str]) -> None:
        """
        Backup database objects metadata.
        """
        for db_name in databases:
            self._backup_database(backup_meta, db_name)

    def restore(self, backup_meta: BackupMetadata, databases: Sequence[str]) -> None:
        """
        Restore database objects.
        """
        present_databases = self._ch_ctl.get_databases()

        for db_name in databases:
            if not _has_embedded_metadata(db_name) and db_name not in present_databases:
                db_sql = self._backup_layout.get_database_create_statement(backup_meta, db_name)
                db_sql = rewrite_database_schema(db_sql, self._config['force_non_replicated'],
                                                 self._config['override_replica_name'])
                logging.debug(f'Restoring database `{db_name}`')
                self._ch_ctl.restore_database(db_sql)

    def restore_schema(self, source_ch_ctl: ClickhouseCTL, databases: Sequence[str], replica_name: str) -> None:
        """
        Restore schema
        """
        present_databases = self._ch_ctl.get_databases()
        databases_to_create = {}
        for database in databases:
            logging.debug('Restoring database "%s"', database)
            db_sql = source_ch_ctl.get_database_schema(database)
            databases_to_create[database] = db_sql

        if databases_to_create:
            if len(self._zk_config.get('hosts')) > 0:
                logging.info("Cleaning up replicated database metadata")
                macros = self._ch_ctl.get_macros()
                zk_ctl = ZookeeperCTL(self._zk_config)
                zk_ctl.delete_replicated_database_metadata(get_database_zookeeper_paths(databases_to_create.values()),
                                                           replica_name, macros)
            for database, db_sql in databases_to_create.items():
                if database in present_databases:
                    if self._ch_ctl.get_database_engine(database) != source_ch_ctl.get_database_engine(database):
                        self._ch_ctl.drop_database_if_exists(database)
                        self._ch_ctl.restore_database(db_sql)
                else:
                    self._ch_ctl.restore_database(db_sql)

    def _backup_database(self, backup_meta: BackupMetadata, db_name: str) -> None:
        """
        Backup database.
        """
        logging.debug('Performing database backup for "%s"', db_name)

        if not _has_embedded_metadata(db_name):
            schema = self._ch_ctl.get_database_schema(db_name)
            self._backup_layout.upload_database_create_statement(backup_meta.name, db_name, schema)

        backup_meta.add_database(db_name)

        self._backup_layout.upload_backup_metadata(backup_meta)


def _has_embedded_metadata(db_name: str) -> bool:
    """
    Return True if db create statement shouldn't be uploaded and applied with restore.
    """
    return db_name in [
        'default',
        'system',
        '_temporary_and_external_tables',
        'information_schema',
        'INFORMATION_SCHEMA',
    ]
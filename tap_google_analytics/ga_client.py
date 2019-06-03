import backoff
import logging

from apiclient.discovery import build
from apiclient.errors import HttpError

from oauth2client.service_account import ServiceAccountCredentials

from tap_google_analytics.error import *

SCOPES = ['https://www.googleapis.com/auth/analytics.readonly']

NON_FATAL_ERRORS = [
  'userRateLimitExceeded',
  'quotaExceeded',
  'internalServerError',
  'backendError'
]

# Silence the discovery_cache errors
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)


class GAClient:
    def __init__(self, config):
        self.client_secrets = config['client_secrets']
        self.view_id = config['view_id']
        self.start_date = config['start_date']
        self.end_date = config['end_date']

        self.analytics = self.initialize_analyticsreporting()

        (self.dimensions_ref, self.metrics_ref) = self.fetch_metadata()

    def initialize_analyticsreporting(self):
        """Initializes an Analytics Reporting API V4 service object.

        Returns:
            An authorized Analytics Reporting API V4 service object.
        """
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
                self.client_secrets, SCOPES)

        # Build the service object.
        analytics = build('analyticsreporting', 'v4', credentials=credentials)

        return analytics

    def fetch_metadata(self):
        """
        Fetch the valid (dimensions, metrics) for the Analytics Reporting API
         and their data types.

        Returns:
          A map of (dimensions, metrics) hashes

          Each available dimension can be found in dimensions with its data type
            as the value. e.g. dimensions['ga:userType'] == STRING

          Each available metric can be found in metrics with its data type
            as the value. e.g. metrics['ga:sessions'] == INTEGER
        """
        metrics = {}
        dimensions = {}

        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
                self.client_secrets, SCOPES)

        # Initialize a Google Analytics API V3 service object and build the service object.
        # This is needed in order to dynamically fetch the metadata for available
        #   metrics and dimensions.
        # (those are not provided in the Analytics Reporting API V4)
        service = build('analytics', 'v3', credentials=credentials)

        results = service.metadata().columns().list(reportType='ga').execute()

        columns = results.get('items', [])

        for column in columns:
            column_attributes = column.get('attributes', [])

            column_name = column.get('id')
            column_type = column_attributes.get('type')
            column_data_type = column_attributes.get('dataType')

            if column_type == 'METRIC':
                metrics[column_name] = column_data_type
            elif column_type == 'DIMENSION':
                dimensions[column_name] = column_data_type

        return (dimensions, metrics)

    def process_stream(self, stream):
        try:
            records = []
            report_definition = self.generate_report_definition(stream)
            nextPageToken = None

            while True:
                response = self.query_api(report_definition, nextPageToken)
                (nextPageToken, results) = self.process_response(response)
                records.extend(results)

                # Keep on looping as long as we have a nextPageToken
                if nextPageToken is None:
                    break

            return records
        except HttpError as e:
            # Process API errors
            # Use list of errors defined in:
            # https://developers.google.com/analytics/devguides/reporting/core/v4/errors

            if e.resp.reason == 'userRateLimitExceeded':
                raise TapGaRateLimitError(e._get_reason())
            elif e.resp.reason == 'quotaExceeded':
                raise TapGaQuotaExceededError(e._get_reason())
            elif e.resp.status == 400:
                raise TapGaInvalidArgumentError(e._get_reason())
            elif e.resp.status in [401, 402]:
                raise TapGaAuthenticationError(e._get_reason())
            else:
                raise TapGaUnknownError(e._get_reason())

    def generate_report_definition(self, stream):
        report_definition = {
            'metrics': [],
            'dimensions': []
        }

        for dimension in stream['dimensions']:
            report_definition['dimensions'].append({'name': dimension.replace("ga_","ga:")})

        for metric in stream['metrics']:
            report_definition['metrics'].append({"expression": metric.replace("ga_","ga:")})

        return report_definition

    def fatal_code(error):
        # Use list of errors defined in:
        # https://developers.google.com/analytics/devguides/reporting/core/v4/errors
        return error.resp.reason not in NON_FATAL_ERRORS

    @backoff.on_exception(backoff.expo,
                          HttpError,
                          max_tries=5,
                          giveup=fatal_code)
    def query_api(self, report_definition, pageToken=None):
        """Queries the Analytics Reporting API V4.

        Returns:
            The Analytics Reporting API V4 response.
        """
        return self.analytics.reports().batchGet(
            body={
                'reportRequests': [
                {
                    'viewId': self.view_id,
                    'dateRanges': [{'startDate': self.start_date, 'endDate': self.end_date}],
                    'pageSize': '1000',
                    'pageToken': pageToken,
                    'metrics': report_definition['metrics'],
                    'dimensions': report_definition['dimensions']
                }]
            }
        ).execute()

    def process_response(self, response):
        """Processes the Analytics Reporting API V4 response.

        Args:
            response: An Analytics Reporting API V4 response.

        Returns: (nextPageToken, results)
            nextPageToken: The next Page Token
             If it is not None then the maximum pageSize has been reached
             and a followup call must be made using self.query_api().
            results: the Analytics Reporting API V4 response as a list of
             dictionaries, e.g.
             [
              {'ga_date': '20190501', 'ga_30dayUsers': '134420',
               'report_start_date': '2019-05-01', 'report_end_date': '2019-05-28'},
               ... ... ...
             ]
        """
        results = []

        try:
            # We always request one report at a time
            report = next(iter(response.get('reports', [])), None)

            columnHeader = report.get('columnHeader', {})
            dimensionHeaders = columnHeader.get('dimensions', [])
            metricHeaders = columnHeader.get('metricHeader', {}).get('metricHeaderEntries', [])

            for row in report.get('data', {}).get('rows', []):
                record = {}
                dimensions = row.get('dimensions', [])
                dateRangeValues = row.get('metrics', [])

                for header, dimension in zip(dimensionHeaders, dimensions):
                    data_type = self.dimensions_ref[header]

                    if data_type == 'INTEGER':
                        value = int(dimension)
                    elif data_type == 'FLOAT' or data_type == 'PERCENT' or data_type == 'TIME':
                        value = float(dimension)
                    else:
                        value = dimension

                    record[header.replace("ga:","ga_")] = value

                for i, values in enumerate(dateRangeValues):
                    for metricHeader, value in zip(metricHeaders, values.get('values')):
                        metric_name = metricHeader.get('name')
                        metric_type = self.metrics_ref[metric_name]

                        if metric_type == 'INTEGER':
                            value = int(value)
                        elif metric_type == 'FLOAT' or metric_type == 'PERCENT' or metric_type == 'TIME':
                            value = float(value)

                        record[metric_name.replace("ga:","ga_")] = value

                # Also add the [start_date,end_date) used for the report
                record['report_start_date'] = self.start_date
                record['report_end_date'] = self.end_date

                results.append(record)

            return (report.get('nextPageToken'), results)
        except StopIteration:
            return (None, [])

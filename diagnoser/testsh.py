#!/usr/bin/env python3


import diagnoser.profiler


def run(config, kafka_consumer, cassandra_client):

    print('SHTest: running Self-Healing test')

    max_iterations = 10
    sleep_time = 30
    min_data = 60
    anomaly_threshold = .25

    data = diagnoser.profiler.load_data(
                cassandra_client,
                config.test_configurations.sh.resource_types,
                config.test_configurations.sh.raw_data_columns,
                config.test_configurations.sh.service_id,
                config.test_configurations.sh.data_ranges,
                config.test_configurations.sh.data_collections,
                config.test_configurations.sh.timestamp,
            )['test0']

    print(data)

    #data, encoders = diagnoser.profiler.profile(
    #            data,
    #            config.test_configurations.sh.learning_columns,
    #            config.test_configurations.sh.test_output_directory,
    #        )

    data_by_app_id = data.groupby('resourcedescription.app_id')
    app_ids = list(data_by_app_id.groups)
    if len(app_ids) < 2:
        print('Not enough appIDs: {}'.format(app_ids))
        return
    app_id = diagnoser.tools.getHigherVersionID(app_ids)
    data = data_by_app_id.get_group(app_id)
    data.set_index('timestamp', inplace=True)
    data = data.resample('S').last().fillna(method='pad')
    data.reset_index(inplace=True)
    print(data)
    print('APP ID IS: {!r}'.format(app_id))
    if len(data) < min_data:
        print('Not really enough data: {}'.format(len(data)))
    alarm_id = "dd062e1f-f0a4-45c6-809b-a9071e9f2dbb"
    anomaly_rating = diagnoser.profiler.evaluate_from_file(
            data[config.test_configurations.sh.learning_columns])
    print('anomaly rating: {}'.format(anomaly_rating))



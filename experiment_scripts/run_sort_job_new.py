"""
This script runs repeated jobs that each sort the same amount of data, using
different numbers of values for each key.
"""

import subprocess

import utils

def check_if_hdfs_file_exists(hdfs_path):
  command = "/root/ephemeral-hdfs/bin/hdfs dfs -ls %s" % hdfs_path
  output = subprocess.Popen(command, stderr=subprocess.PIPE, shell=True).communicate()
  index = (output[1].find("No such file"))
  return (index == -1)

target_total_data_gb = 200
# HDFS blocks are actually 128MB; round down here so that none of the output monotasks
# end up writing data to two different blocks, which we don't handle correctly.
hdfs_blocks_per_gb = 1024 / 105

slaves = [slave_line.strip("\n") for slave_line in open("/root/spark/conf/slaves").readlines()]
print "Running experiment assuming slaves %s" % slaves

num_machines = len(slaves)
values_per_key_values = [10, 25, 100, 1]
num_tasks = target_total_data_gb * hdfs_blocks_per_gb
# Just do one trial for now! When experiment is properly configured, do many trials.
num_shuffles = 3
cores_per_worker_values = [8, 4]

for cores_per_worker in cores_per_worker_values:
  # Change the number of concurrent tasks by re-setting the Spark config.
  change_cores_command = ("sed -i s/SPARK_WORKER_CORES=.*/SPARK_WORKER_CORES=" +
    "%s/ /root/spark/conf/spark-env.sh" % cores_per_worker)
  print "Changing the number of Spark cores using command ", change_cores_command
  subprocess.check_call(change_cores_command, shell=True)

  copy_config_command = "/root/spark-ec2/copy-dir --delete /root/spark/conf/"
  print "Copying the new configuration to the cluster with command ", copy_config_command
  subprocess.check_call(copy_config_command, shell=True)

  # Need to stop and re-start Spark, so that the new number of cores per worker takes effect.
  subprocess.check_call("/root/spark/sbin/stop-all.sh")
  subprocess.check_call("/root/spark/sbin/start-all.sh")

  for values_per_key in values_per_key_values:
    total_num_items = target_total_data_gb / (4.9 + values_per_key * 1.92) * (64 * 4000000)
    items_per_task =  int(total_num_items / num_tasks)
    data_filename = "randomData_%s_%sGB_105target" % (values_per_key, target_total_data_gb)
    use_existing_data_files = check_if_hdfs_file_exists(data_filename)
    # The cores_per_worker parameter won't be used by the experiment; it's just included here for
    # convenience in how the log files are named.
    parameters = [num_tasks, num_tasks, items_per_task, values_per_key, num_shuffles,
      data_filename, use_existing_data_files, cores_per_worker]
    stringified_parameters = ["%s" % p for p in parameters]
    command = "/root/spark/bin/run-example SortJob %s" % " ".join(stringified_parameters)
    print command
    subprocess.check_call(command, shell=True)

    utils.copy_and_zip_all_logs(stringified_parameters, slaves)

    # Clear the buffer cache, to sidestep issue with machines dying.
    subprocess.check_call("/root/ephemeral-hdfs/sbin/slaves.sh /root/spark-ec2/clear-cache.sh", shell=True)

    # Delete any sorted data.
    subprocess.check_call("/root/ephemeral-hdfs/bin/hadoop dfs -rm -r ./*sorted*", shell=True)

  # Future numbers of cores_per_worker don't need to re-generate the data files, and can instead just use the existing ones.
  use_existing_data_files = True
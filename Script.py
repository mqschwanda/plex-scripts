#!/usr/bin/python

import ConfigParser
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
###
# Exit on wrong format of startup code
if len(sys.argv) < 2:
  print "Usage: python '{0}' <path_to_file>".format(os.path.realpath(__file__))
  sys.exit(1)
###
# Configure process from file
config_file_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.conf')
if not os.path.exists(config_file_path): # check for config file and exit process if it does not exist
  print "Config file not found: '{0}'".format(config_file_path)
  print 'Make a copy of config.conf.example named config.conf, modify as necessary, and place in the same directory as this script.'
  sys.exit(1)
###
# Handle config file parse
config = ConfigParser.SafeConfigParser({'comskip-ini-path' : os.path.join(os.path.dirname(os.path.realpath(__file__)), 'comskip.ini'), 'temp-root' : tempfile.gettempdir(), 'nice-level' : '0'})
config.read(config_file_path) # read the file into configuration
###
# Bring in global variables from os and config
COMSKIP_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'comskip-path')))
COMSKIP_INI_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'comskip-ini-path')))
FFMPEG_PATH = os.path.expandvars(os.path.expanduser(config.get('Helper Apps', 'ffmpeg-path')))
LOG_FILE_PATH = os.path.expandvars(os.path.expanduser(config.get('Logging', 'logfile-path')))
CONSOLE_LOGGING = config.getboolean('Logging', 'console-logging')
TEMP_ROOT = os.path.expandvars(os.path.expanduser(config.get('File Manipulation', 'temp-root')))
COPY_ORIGINAL = config.getboolean('File Manipulation', 'copy-original')
SAVE_ALWAYS = config.getboolean('File Manipulation', 'save-always')
SAVE_FORENSICS = config.getboolean('File Manipulation', 'save-forensics')
NICE_LEVEL = config.get('Helper Apps', 'nice-level')
###
# Handle Logging
session_uuid = str(uuid.uuid4())
fmt = "%%(asctime)-15s ['{0}'] %%(message)s".format(session_uuid[:6])
if not os.path.exists(os.path.dirname(LOG_FILE_PATH)):
  os.makedirs(os.path.dirname(LOG_FILE_PATH))
logging.basicConfig(level=logging.INFO, format=fmt, filename=LOG_FILE_PATH)
if CONSOLE_LOGGING:
  console = logging.StreamHandler()
  console.setLevel(logging.INFO)
  formatter = logging.Formatter('%(message)s')
  console.setFormatter(formatter)
  logging.getLogger('').addHandler(console)
###
# Human-readable bytes conversion
def sizeof_fmt(num, suffix='B'):
  for unit in ['','K','M','G','T','P','E','Z']:
    if abs(num) < 1024.0:
      return "%3.1f%s%s" % (num, unit, suffix)
    num /= 1024.0
  return "%.1f%s%s" % (num, 'Y', suffix)
###
# Compress with FFMPEG.
def compress_video(compress_video_path):
  try:
    logging.info('Starting video compression!')
    compressed_output = os.path.join(original_video_dir, '.'.join([video_name,'mp4']))
    FFMPEG = [FFMPEG_PATH, '-y', '-i', compress_video_path, compressed_output]
    video_format = ['-vcodec', 'h264', '-r', '30', '-crf', '20', '-vf', "scale=min'(1920,iw)':-2", '-movflags', 'faststart']
    audio_format = ['-acodec', 'aac','-ab','128k']
    cmd = NICE_ARGS + FFMPEG + video_format + audio_format
    logging.info("[FFMPEG] Command: '{0}'".format(cmd))
    subprocess.call(cmd)
    logging.info('Done compressing!')
    try:
      if os.path.exists(compress_video_path) and os.path.exists(compressed_output):
        logging.info('Removing original file...')
        os.remove(compress_video_path)
      elif os.path.exists(compressed_output):
        logging.info('Could only find processed file... original file is already deleted.')
      elif os.path.exists(compress_video_path):
        logging.info('Could only find original file... will not delete orignal.')
      else:
        logging.info('Could not find any files...')

    except Exception, e:
      logging.error('Something went wrong while consolidating files: %s' % e)
      cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)

  except Exception, e:
    logging.error('Problem compressing file: %s' % compress_video_path)
    logging.error(str(e))

# Clean up after ourselves and exit.
def cleanup_and_exit(temp_dir, keep_temp=False):
  if keep_temp:
    logging.info('Leaving temp files in: %s' % temp_dir)
  else:
    try:
      os.chdir(os.path.expanduser('~'))  # Get out of the temp dir before we nuke it (causes issues on NTFS)
      shutil.rmtree(temp_dir)
    except Exception, e:
      logging.error('Problem whacking temp dir: %s' % temp_dir)
      logging.error(str(e))

  # Exit cleanly.
  logging.info('Done processing!')
  sys.exit(0)

def check_comskip_output():
  logging.info('Analyzing ComSkip output file...')
  try:
    input_size = os.path.getsize(video_path)
    output_size = os.path.getsize(os.path.join(temp_dir, video_basename))
    if input_size and 1.01 > float(output_size) / float(input_size) > 0.99: # file size is between 99% and 101% of original
      logging.info('No comercials were found, the original file will not be replaced')
      compress_video(video_path) # Compress with FFMPEG.
      cleanup_and_exit(temp_dir, SAVE_ALWAYS)
    elif input_size and 1 > float(output_size) / float(input_size) > 0.5: # file size is between 50% and 100% of original
      size_change = sizeof_fmt(input_size - output_size)
      percent_change = int(output_size / input_size)
      logging.info("Comercials were found, the original file has been reduced by '{0}' ('{1}'%)".format(size_change, percent_change))
      # logging.info('Comskip output file size looked sane, we\'ll replace the original: %s -> %s' % (sizeof_fmt(input_size), sizeof_fmt(output_size)))
      try:
        comskip_output = os.path.join(temp_dir, video_basename)
        compress_video(comskip_output) # Compress with FFMPEG.
        cleanup_and_exit(temp_dir, SAVE_ALWAYS)
      except Exception, e:
        logging.error('Something went wrong during FFMPEG compression: %s' % e)
        logging.info('Copying Comskip output file into place: %s -> %s' % (video_basename, original_video_dir))
        shutil.copy(os.path.join(temp_dir, video_basename), original_video_dir)
        cleanup_and_exit(temp_dir, SAVE_ALWAYS)
    else:
      logging.info('Comskip output file size looked wonky (too big or too small); we won\'t replace the original: %s -> %s' % (sizeof_fmt(input_size), sizeof_fmt(output_size)))
      cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)
  except Exception, e:
    logging.error('Something went wrong during sanity check: %s' % e)
    cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)

# If we're in a git repo, let's see if we can report our sha.
logging.info('PlexScript got invoked from %s' % os.path.realpath(__file__))
try:
  git_sha = subprocess.check_output('git rev-parse --short HEAD', shell=True)
  if git_sha:
    logging.info('Using version: %s' % git_sha.strip())
except: pass

# Set our own nice level and tee up some args for subprocesses (unix-like OSes only).
NICE_ARGS = []
if sys.platform != 'win32':
  try:
    nice_int = max(min(int(NICE_LEVEL), 20), 0)
    if nice_int > 0:
      os.nice(nice_int)
      NICE_ARGS = ['nice', '-n', str(nice_int)]
  except Exception, e:
    logging.error('Couldn\'t set nice level to %s: %s' % (NICE_LEVEL, e))

# On to the actual work.
try:
  video_path = sys.argv[1]
  temp_dir = os.path.join(TEMP_ROOT, session_uuid)
  os.makedirs(temp_dir)
  os.chdir(temp_dir)

  logging.info('Using session ID: %s' % session_uuid)
  logging.info('Using temp dir: %s' % temp_dir)
  logging.info('Using input file: %s' % video_path)

  original_video_dir = os.path.dirname(video_path)
  video_basename = os.path.basename(video_path)
  video_name, video_ext = os.path.splitext(video_basename)

except Exception, e:
  logging.error('Something went wrong setting up temp paths and working files: %s' % e)
  sys.exit(0)

try:
  if COPY_ORIGINAL or SAVE_ALWAYS:
    temp_video_path = os.path.join(temp_dir, video_basename)
    logging.info('Copying file to work on it: %s' % temp_video_path)
    shutil.copy(video_path, temp_dir)
  else:
    temp_video_path = video_path

  # Process with comskip.
  cmd = NICE_ARGS + [COMSKIP_PATH, '--output', temp_dir, '--ini', COMSKIP_INI_PATH, temp_video_path]
  logging.info('[comskip] Command: %s' % cmd)
  subprocess.call(cmd)

except Exception, e:
  logging.error('Something went wrong during comskip analysis: %s' % e)
  cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)

edl_file = os.path.join(temp_dir, video_name + '.edl')
logging.info('Using EDL: ' + edl_file)
try:
  segments = []
  prev_segment_end = 0.0
  if os.path.exists(edl_file):
    with open(edl_file, 'rb') as edl:

      # EDL contains segments we need to drop, so chain those together into segments to keep.
      for segment in edl:
        start, end, something = segment.split()
        if float(start) == 0.0:
          logging.info('Start of file is junk, skipping this segment...')
        else:
          keep_segment = [float(prev_segment_end), float(start)]
          logging.info('Keeping segment from %s to %s...' % (keep_segment[0], keep_segment[1]))
          segments.append(keep_segment)
        prev_segment_end = end

  # Write the final keep segment from the end of the last commercial break to the end of the file.
  keep_segment = [float(prev_segment_end), -1]
  logging.info('Keeping segment from %s to the end of the file...' % prev_segment_end)
  segments.append(keep_segment)

  segment_files = []
  segment_list_file_path = os.path.join(temp_dir, 'segments.txt')
  with open(segment_list_file_path, 'wb') as segment_list_file:
    for i, segment in enumerate(segments):
      segment_name = 'segment-%s' % i
      segment_file_name = '%s%s' % (segment_name, video_ext)
      if segment[1] == -1:
        duration_args = []
      else:
        duration_args = ['-t', str(segment[1] - segment[0])]
      cmd = NICE_ARGS + [FFMPEG_PATH, '-i', temp_video_path, '-ss', str(segment[0])]
      cmd.extend(duration_args)
      cmd.extend(['-c', 'copy', segment_file_name])
      logging.info('[ffmpeg] Command: %s' % cmd)
      try:
        subprocess.call(cmd)
      except Exception, e:
        logging.error('Exception running ffmpeg: %s' % e)
        cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)

      # If the last drop segment ended at the end of the file, we will have written a zero-duration file.
      if os.path.exists(segment_file_name):
        if os.path.getsize(segment_file_name) < 1000:
          logging.info('Last segment ran to the end of the file, not adding bogus segment %s for concatenation.' % (i + 1))
          continue

        segment_files.append(segment_file_name)
        segment_list_file.write('file %s\n' % segment_file_name)

except Exception, e:
  logging.error('Something went wrong during splitting: %s' % e)
  cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)

logging.info('Going to concatenate %s files from the segment list.' % len(segment_files))
try:
  cmd = NICE_ARGS + [FFMPEG_PATH, '-y', '-f', 'concat', '-i', segment_list_file_path, '-c', 'copy', os.path.join(temp_dir, video_basename)]
  logging.info('[ffmpeg] Command: %s' % cmd)
  subprocess.call(cmd)

except Exception, e:
  logging.error('Something went wrong during concatenation: %s' % e)
  cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)

check_comskip_output()
# logging.info('Sanity checking our work...')
# try:
#   input_size = os.path.getsize(video_path)
#   output_size = os.path.getsize(os.path.join(temp_dir, video_basename))
#   if input_size and 1.01 > float(output_size) / float(input_size) > 0.99:
#     logging.info('Comskip output file size was too similar (doesn\'t look like we did much); we won\'t replace the original: %s -> %s' % (sizeof_fmt(input_size), sizeof_fmt(output_size)))
#     cleanup_and_exit(temp_dir, SAVE_ALWAYS)
#   elif input_size and 1.1 > float(output_size) / float(input_size) > 0.5:
#     logging.info('Comskip output file size looked sane, we\'ll replace the original: %s -> %s' % (sizeof_fmt(input_size), sizeof_fmt(output_size)))
#     try:
#       comskip_output = os.path.join(temp_dir, video_basename)
#       compress_video(comskip_output) # Compress with FFMPEG.
#       cleanup_and_exit(temp_dir, SAVE_ALWAYS)
#     except Exception, e:
#       logging.error('Something went wrong during FFMPEG compression: %s' % e)
#       logging.info('Copying Comskip output file into place: %s -> %s' % (video_basename, original_video_dir))
#       shutil.copy(os.path.join(temp_dir, video_basename), original_video_dir)
#       cleanup_and_exit(temp_dir, SAVE_ALWAYS)
#   else:
#     logging.info('Comskip output file size looked wonky (too big or too small); we won\'t replace the original: %s -> %s' % (sizeof_fmt(input_size), sizeof_fmt(output_size)))
#     cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)
# except Exception, e:
#   logging.error('Something went wrong during sanity check: %s' % e)
#   cleanup_and_exit(temp_dir, SAVE_ALWAYS or SAVE_FORENSICS)

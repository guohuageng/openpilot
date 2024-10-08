#!/usr/bin/env python3
import datetime
import os
import signal
import sys
import traceback

from cereal import log
import cereal.messaging as messaging
import openpilot.system.sentry as sentry
from openpilot.common.params import Params, ParamKeyType
from openpilot.common.text_window import TextWindow
from openpilot.system.hardware import HARDWARE, PC
from openpilot.system.manager.helpers import unblock_stdout, write_onroad_params, save_bootlog
from openpilot.system.manager.process import ensure_running
from openpilot.system.manager.process_config import managed_processes
from openpilot.system.athena.registration import register, UNREGISTERED_DONGLE_ID
from openpilot.common.swaglog import cloudlog, add_file_handler
from openpilot.system.version import get_build_metadata, terms_version, training_version

def manager_init() -> None:
  save_bootlog()  # 保存启动日志

  build_metadata = get_build_metadata()  # 获取构建元数据

  params = Params()
  params.clear_all(ParamKeyType.CLEAR_ON_MANAGER_START)  # 清除所有在管理器启动时清除的参数
  params.clear_all(ParamKeyType.CLEAR_ON_ONROAD_TRANSITION)  # 清除所有在上路过渡时清除的参数
  params.clear_all(ParamKeyType.CLEAR_ON_OFFROAD_TRANSITION)  # 清除所有在离路过渡时清除的参数
  if build_metadata.release_channel:
    params.clear_all(ParamKeyType.DEVELOPMENT_ONLY)  # 如果是发布渠道，清除所有仅开发参数
  default_params: list[tuple[str, str | bytes]] = [
    ("CompletedTrainingVersion", "0"),  # 完成培训版本
    ("DisengageOnAccelerator", "0"),  # 加速器脱离
    ("GsmMetered", "1"),  # GSM计量
    ("HasAcceptedTerms", "0"),  # 已接受条款
    ("LanguageSetting", "main_zh-CHT"),  # 语言设置
    ("OpenpilotEnabledToggle", "1"),  # Openpilot启用切换
    ("LongitudinalPersonality", str(log.LongitudinalPersonality.standard)),  # 纵向个性

    # dp
    ("dp_device_display_off_mode", "0"),  # 设备显示关闭模式
    ("dp_ui_rainbow", "0"),  # UI彩虹模式
    ("dp_ui_flight_panel", "0"),  # UI飞行面板
    ("dp_long_de2e", "0"),  # 长期de2e
    ("dp_long_personality_btn", "0"),  # 长期个性按钮
    ("dp_ui_map_full", "0"),  # UI全地图
    ("dp_alka", "0"),  # Alka
    ("dp_device_ip_addr", ""),  # 设备IP地址
    ("dp_vag_sng", "0"),  # VAG SNG
    ("dp_vehicle_list", ""),  # 车辆列表
    ("dp_vehicle_assigned", ""),  # 分配的车辆
    ("dp_nav_free_map", "0"),  # 免费地图导航
    ("dp_nav_name", "0"),  # 导航名称
    ("dp_nav_traffic", "0"),  # 导航交通
    ("dp_toyota_auto_lock", "0"),  # 丰田自动锁
    ("dp_toyota_auto_unlock", "0"),  # 丰田自动解锁
    ("dp_device_disable_onroad_uploads", "0"),  # 禁用道路上传
    ("dp_toyota_zss", "0"),  # 丰田ZSS
    ("dp_hkg_canfd_low_speed_turn_enhancer", "0"),  # HKG CANFD低速转弯增强器
    ("dp_long_alt_driving_personality_mode", "0"),  # 长期备用驾驶个性模式
    ("dp_long_alt_driving_personality_speed", "0"),  # 长期备用驾驶个性速度
    ("dp_long_curve_speed_limiter", "0"),  # 长期曲线速度限制器
    ("dp_lat_lane_change_assist_mode", "0"),  # 车道变更辅助模式
    ("dp_lat_lane_change_assist_speed", "32"),  # 车道变更辅助速度
    ("dp_lat_lane_change_assist_auto_timer", "1.5"),  # 车道变更辅助自动计时器
    ("dp_lat_road_edge_detection", "0"),  # 道路边缘检测
    ("dp_device_disable_logging", "0"),  # 禁用设备日志记录
    ("dp_toyota_pcm_compensation", "0"),  # 丰田PCM补偿
    ("dp_device_is_clone", "0"),  # 设备是克隆
    ("dp_device_dm_unavailable", "0"),  # 设备DM不可用
    ("dp_toyota_enhanced_bsm", "0"),  # 丰田增强BSM
    ("dp_toyota_auto_brake_hold", "0"),  # 丰田自动刹车保持
    ("dp_toyota_sng", "0"),  # 丰田SNG
    ("dp_tetoo", "0"),  # Tetoo
    ("dp_tetoo_data", ""),  # Tetoo数据
    ("dp_tetoo_gps", ""),  # Tetoo GPS
    ("dp_tetoo_speed_camera_taiwan", "0"),  # Tetoo台湾测速摄像头
    ("dp_tetoo_speed_camera_threshold", "0"),  # Tetoo测速摄像头阈值
    ("dp_long_de2e_road_condition", "1"),  # 长期de2e道路状况，默认开启
    ("dp_device_auto_shutdown", "0"),  # 设备自动关机
    ("dp_device_auto_shutdown_in", "30"),  # 设备自动关机时间
    ("dp_device_audible_alert_mode", "0"),  # 设备声音警报模式
    ("dp_long_pal", "0"),  # 长期PAL
    ("dp_long_pal_freeze", "0"),  # 长期PAL冻结
    ("dp_long_pal_launch_boost", "0"),  # 长期PAL启动加速
    ("dp_vag_pq_steering_patch", "0"),  # VAG PQ转向补丁
    ("dp_lat_lane_priority_mode", "0"),  # 车道优先模式
    ("dp_lat_lane_priority_mode_speed", "0"),  # 车道优先模式速度
    ("dp_lat_lane_priority_mode_camera_offset", "4"),  # 车道优先模式摄像头偏移
  ]
  if not PC:
    default_params.append(("LastUpdateTime", datetime.datetime.now(datetime.UTC).replace(tzinfo=None).isoformat().encode('utf8')))  # 添加最后更新时间

  params.put("dp_vehicle_list", get_support_vehicle_list())  # 设置支持车辆列表

  if params.get_bool("RecordFrontLock"):
    params.put_bool("RecordFront", True)  # 如果前置记录锁定，设置前置记录为真

  # 设置未设置的参数
  for k, v in default_params:
    if params.get(k) is None:
      params.put(k, v)

  # 创建msgq所需的文件夹
  try:
    os.mkdir("/dev/shm")
  except FileExistsError:
    pass
  except PermissionError:
    print("WARNING: failed to make /dev/shm")  # 警告：创建/dev/shm失败

  # 设置版本参数
  params.put("Version", build_metadata.openpilot.version)
  params.put("TermsVersion", terms_version)
  params.put("TrainingVersion", training_version)
  params.put("GitCommit", build_metadata.openpilot.git_commit)
  params.put("GitCommitDate", build_metadata.openpilot.git_commit_date)
  params.put("GitBranch", build_metadata.channel)
  params.put("GitRemote", build_metadata.openpilot.git_origin)
  params.put_bool("IsTestedBranch", build_metadata.tested_channel)
  params.put_bool("IsReleaseBranch", build_metadata.release_channel)

  # 设置dongle id
  reg_res = register(show_spinner=True)
  if reg_res:
    dongle_id = reg_res
  else:
    serial = params.get("HardwareSerial")
    raise Exception(f"Registration failed for device {serial}")  # 设备注册失败
  os.environ['DONGLE_ID'] = dongle_id  # 需要用于swaglog
  os.environ['GIT_ORIGIN'] = build_metadata.openpilot.git_normalized_origin  # 需要用于swaglog
  os.environ['GIT_BRANCH'] = build_metadata.channel  # 需要用于swaglog
  os.environ['GIT_COMMIT'] = build_metadata.openpilot.git_commit  # 需要用于swaglog

  if not build_metadata.openpilot.is_dirty:
    os.environ['CLEAN'] = '1'

  # 初始化日志记录
  sentry.init(sentry.SentryProject.SELFDRIVE)
  cloudlog.bind_global(dongle_id=dongle_id,
                       version=build_metadata.openpilot.version,
                       origin=build_metadata.openpilot.git_normalized_origin,
                       branch=build_metadata.channel,
                       commit=build_metadata.openpilot.git_commit,
                       dirty=build_metadata.openpilot.is_dirty,
                       device=HARDWARE.get_device_type())

  # 预导入所有进程
  for p in managed_processes.values():
    p.prepare()

def manager_cleanup() -> None:
  # 发送信号以终止所有进程
  for p in managed_processes.values():
    p.stop(block=False)

  # 确保所有进程都已终止
  for p in managed_processes.values():
    p.stop(block=True)

  cloudlog.info("everything is dead")  # 所有进程都已终止

def manager_thread() -> None:
  cloudlog.bind(daemon="manager")
  cloudlog.info("manager start")  # 管理器启动
  cloudlog.info({"environ": os.environ})

  params = Params()

  ignore: list[str] = []
  # dp
  dp_device_dm_unavailable = params.get_bool("dp_device_dm_unavailable")
  dp_device_is_clone = params.get_bool("dp_device_is_clone")
  if dp_device_is_clone or dp_device_dm_unavailable:
    ignore += ["manage_athenad", "uploader"]
    if dp_device_dm_unavailable:
      ignore += ["dmonitoringd", "dmonitoringmodeld"]

  if params.get("DongleId", encoding='utf8') in (None, UNREGISTERED_DONGLE_ID):
    ignore += ["manage_athenad", "uploader"]
  if os.getenv("NOBOARD") is not None:
    ignore.append("pandad")
  ignore += [x for x in os.getenv("BLOCK", "").split(",") if len(x) > 0]

  sm = messaging.SubMaster(['deviceState', 'carParams'], poll='deviceState')
  pm = messaging.PubMaster(['managerState'])

  write_onroad_params(False, params)  # 写入上路参数
  ensure_running(managed_processes.values(), False, params=params, CP=sm['carParams'], not_run=ignore)  # 确保进程运行

  started_prev = False

  while True:
    sm.update(1000)

    started = sm['deviceState'].started

    if started and not started_prev:
      params.clear_all(ParamKeyType.CLEAR_ON_ONROAD_TRANSITION)  # 清除所有在上路过渡时清除的参数
    elif not started and started_prev:
      params.clear_all(ParamKeyType.CLEAR_ON_OFFROAD_TRANSITION)  # 清除所有在离路过渡时清除的参数

    # 更新上路参数，驱动pandad的安全设置线程
    if started != started_prev:
      write_onroad_params(started, params)

    started_prev = started

    ensure_running(managed_processes.values(), started, params=params, CP=sm['carParams'], not_run=ignore)  # 确保进程运行

    running = ' '.join("{}{}\u001b[0m".format("\u001b[32m" if p.proc.is_alive() else "\u001b[31m", p.name)
                       for p in managed_processes.values() if p.proc)
    print(running)
    cloudlog.debug(running)

    # 发送managerState
    msg = messaging.new_message('managerState', valid=True)
    msg.managerState.processes = [p.get_process_state_msg() for p in managed_processes.values()]
    pm.send('managerState', msg)

    # 当需要卸载/关机/重启时退出主循环
    shutdown = False
    for param in ("DoUninstall", "DoShutdown", "DoReboot", "dp_device_reset_conf"):
      if params.get_bool(param):
        if param == "dp_device_reset_conf":
          os.system("rm -fr /data/params/d/dp_*")
        shutdown = True
        params.put("LastManagerExitReason", f"{param} {datetime.datetime.now()}")
        cloudlog.warning(f"Shutting down manager - {param} set")  # 关闭管理器 - 设置了{param}

    if shutdown:
      break

def main() -> None:
  manager_init()
  if os.getenv("PREPAREONLY") is not None:
    return

  # 在sigterm上SystemExit
  signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(1))

  try:
    manager_thread()
  except Exception:
    traceback.print_exc()
    sentry.capture_exception()
  finally:
    manager_cleanup()

  params = Params()
  if params.get_bool("DoUninstall"):
    cloudlog.warning("uninstalling")  # 卸载中
    HARDWARE.uninstall()
  elif params.get_bool("DoReboot"):
    cloudlog.warning("reboot")  # 重启
    HARDWARE.reboot()
  elif params.get_bool("DoShutdown"):
    cloudlog.warning("shutdown")  # 关机
    HARDWARE.shutdown()

def get_support_vehicle_list():
  from openpilot.selfdrive.car.fingerprints import all_known_cars, all_legacy_fingerprint_cars
  import json
  cars = dict({"cars": []})
  list = []
  for car in all_known_cars():
    list.append(str(car))

  for car in all_legacy_fingerprint_cars():
    name = str(car)
    if name not in list:
      list.append(name)
  cars["cars"] = sorted(list)
  return json.dumps(cars)

if __name__ == "__main__":
  unblock_stdout()

  try:
    main()
  except KeyboardInterrupt:
    print("got CTRL-C, exiting")  # 收到CTRL-C，退出
  except Exception:
    add_file_handler(cloudlog)
    cloudlog.exception("Manager failed to start")  # 管理器启动失败

    try:
      managed_processes['ui'].stop()
    except Exception:
      pass

    # 显示最后3行回溯
    error = traceback.format_exc(-3)
    error = "Manager failed to start\n\n" + error
    with TextWindow(error) as t:
      t.wait_for_exit()

    raise

  # 手动退出，因为我们是forked
  sys.exit(0)

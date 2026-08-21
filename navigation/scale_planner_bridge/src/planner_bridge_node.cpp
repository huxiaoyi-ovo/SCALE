#include <costmap_2d/costmap_2d_ros.h>
#include <geometry_msgs/TransformStamped.h>
#include <nav_core/base_local_planner.h>
#include <nav_msgs/Odometry.h>
#include <pluginlib/class_loader.hpp>
#include <ros/callback_queue.h>
#include <rosgraph_msgs/Clock.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2_ros/buffer.h>

#include <scale_planner_bridge/Initialize.h>
#include <scale_planner_bridge/Step.h>

#include <chrono>
#include <cmath>
#include <cstdint>
#include <memory>
#include <stdexcept>
#include <string>

namespace {
constexpr double kClockEpoch = 1.0;
constexpr double kTimeTolerance = 1e-9;

geometry_msgs::Quaternion quaternion(double yaw) {
  tf2::Quaternion q;
  q.setRPY(0.0, 0.0, yaw);
  geometry_msgs::Quaternion result;
  result.x = q.x(); result.y = q.y(); result.z = q.z(); result.w = q.w();
  return result;
}

bool same(double left, double right) {
  return std::abs(left - right) <= kTimeTolerance;
}
}  // namespace

class PlannerBridge {
 public:
  PlannerBridge()
      : nh_(), private_nh_("~"), service_nh_(),
        loader_("nav_core", "nav_core::BaseLocalPlanner"), tf_(ros::Duration(10.0)) {
    bool use_sim_time = false;
    nh_.param("/use_sim_time", use_sim_time, false);
    if (!use_sim_time) throw std::runtime_error("/use_sim_time must be true");

    private_nh_.param<std::string>("planner_plugin", planner_plugin_, "dwa_local_planner/DWAPlannerROS");
    private_nh_.param<std::string>("global_frame", global_frame_, "map");
    private_nh_.param<std::string>("base_frame", base_frame_, "base_link");
    private_nh_.param<std::string>("odom_topic", odom_topic_, "odom");
    private_nh_.param("allow_reinitialize", allow_reinitialize_, false);

    service_nh_.setCallbackQueue(&service_queue_);
    clock_pub_ = nh_.advertise<rosgraph_msgs::Clock>("/clock", 1, true);
    setLogicalTime(0.0);

    tf_.setUsingDedicatedThread(true);
    geometry_msgs::TransformStamped initial_transform;
    initial_transform.header.stamp = ros::Time::now();
    initial_transform.header.frame_id = global_frame_;
    initial_transform.child_frame_id = base_frame_;
    initial_transform.transform.rotation.w = 1.0;
    tf_.setTransform(initial_transform, "scale_planner_bridge", true);
    costmap_.reset(new costmap_2d::Costmap2DROS("local_costmap", tf_));
    costmap_->pause();

    odom_pub_ = nh_.advertise<nav_msgs::Odometry>(odom_topic_, 1);
    initialize_srv_ = service_nh_.advertiseService("initialize", &PlannerBridge::initialize, this);
    step_srv_ = service_nh_.advertiseService("step", &PlannerBridge::step, this);
  }

  ros::CallbackQueue* serviceQueue() { return &service_queue_; }

 private:
  void setLogicalTime(double simulation_time) {
    const ros::Time logical_time(kClockEpoch + simulation_time);
    ros::Time::setNow(logical_time);
    rosgraph_msgs::Clock clock;
    clock.clock = logical_time;
    clock_pub_.publish(clock);
  }

  bool initialize(scale_planner_bridge::Initialize::Request& request,
                  scale_planner_bridge::Initialize::Response& response) {
    if (initialized_ && !allow_reinitialize_) {
      response.ok = false; response.error = "bridge is already initialized"; return true;
    }
    if (request.planner_period <= 0.0 || !std::isfinite(request.planner_period)) {
      response.ok = false; response.error = "planner_period must be finite and positive"; return true;
    }
    if (request.map.info.resolution <= 0.0 || request.map.info.width == 0 || request.map.info.height == 0 ||
        request.map.data.size() != request.map.info.width * request.map.info.height || request.plan.poses.empty()) {
      response.ok = false; response.error = "map or plan is invalid"; return true;
    }

    if (initialized_) {
      odom_echo_sub_.shutdown();
      planner_.reset();
      echoed_odom_ = nav_msgs::Odometry();
      odom_callbacks_ = 0;
      step_index_ = 0;
      initialized_ = false;
    }

    planner_period_ = request.planner_period;
    private_nh_.setParam("controller_frequency", 1.0 / planner_period_);
    costmap_2d::Costmap2D* map = costmap_->getCostmap();
    map->resizeMap(request.map.info.width, request.map.info.height, request.map.info.resolution,
                   request.map.info.origin.position.x, request.map.info.origin.position.y);
    for (unsigned int y = 0; y < request.map.info.height; ++y) {
      for (unsigned int x = 0; x < request.map.info.width; ++x) {
        const int8_t value = request.map.data[y * request.map.info.width + x];
        map->setCost(x, y, value >= 50 ? costmap_2d::LETHAL_OBSTACLE : costmap_2d::FREE_SPACE);
      }
    }

    try {
      planner_ = loader_.createInstance(planner_plugin_);
      planner_->initialize("planner", &tf_, costmap_.get());
      odom_echo_sub_ = nh_.subscribe(odom_topic_, 1, &PlannerBridge::odomEcho, this);
      const ros::WallTime deadline = ros::WallTime::now() + ros::WallDuration(1.0);
      // roscpp shares one intraprocess transport for same-node subscribers on
      // the same topic, then fans the message out to both planner and audit
      // callbacks.  Drain the shared queue below before planning.
      while (ros::ok() && odom_pub_.getNumSubscribers() < 1 && ros::WallTime::now() < deadline) {
        ros::getGlobalCallbackQueue()->callAvailable(ros::WallDuration(0.005));
      }
      if (odom_pub_.getNumSubscribers() < 1) {
        response.ok = false; response.error = "shared planner/audit odom connection did not form"; return true;
      }
      if (!planner_->setPlan(request.plan.poses)) {
        response.ok = false; response.error = "plugin rejected fixed global plan"; return true;
      }
    } catch (const pluginlib::PluginlibException& error) {
      response.ok = false; response.error = error.what(); return true;
    }

    initialized_ = true;
    response.ok = true;
    response.clock_epoch = kClockEpoch;
    return true;
  }

  bool step(scale_planner_bridge::Step::Request& request,
            scale_planner_bridge::Step::Response& response) {
    if (!initialized_) {
      response.ok = false; response.error = "initialize must be called first"; return true;
    }
    const double expected_time = static_cast<double>(step_index_) * planner_period_;
    if (!std::isfinite(request.simulation_time) || !same(request.simulation_time, expected_time)) {
      response.ok = false;
      response.error = "simulation_time does not match the fixed planner schedule";
      return true;
    }
    setLogicalTime(request.simulation_time);
    const ros::Time stamp = ros::Time::now();

    geometry_msgs::TransformStamped transform;
    transform.header.stamp = stamp; transform.header.frame_id = global_frame_; transform.child_frame_id = base_frame_;
    transform.transform.translation.x = request.x; transform.transform.translation.y = request.y;
    transform.transform.rotation = quaternion(request.yaw);
    try {
      tf_.setTransform(transform, "scale_planner_bridge", true);
    } catch (const tf2::TransformException& error) {
      response.ok = false; response.error = error.what(); return true;
    }

    nav_msgs::Odometry odom;
    odom.header.stamp = stamp; odom.header.frame_id = global_frame_; odom.child_frame_id = base_frame_;
    odom.pose.pose.position.x = request.x; odom.pose.pose.position.y = request.y;
    odom.pose.pose.orientation = quaternion(request.yaw);
    odom.twist.twist.linear.x = request.vx; odom.twist.twist.linear.y = request.vy;
    odom.twist.twist.angular.z = request.wz;

    const uint64_t previous_callbacks = odom_callbacks_;
    odom_pub_.publish(odom);
    const ros::WallTime deadline = ros::WallTime::now() + ros::WallDuration(0.2);
    while (ros::ok() && odom_callbacks_ == previous_callbacks && ros::WallTime::now() < deadline) {
      ros::getGlobalCallbackQueue()->callAvailable(ros::WallDuration(0.005));
    }
    while (!ros::getGlobalCallbackQueue()->isEmpty()) {
      ros::getGlobalCallbackQueue()->callAvailable(ros::WallDuration(0.0));
    }
    if (odom_callbacks_ == previous_callbacks) {
      response.ok = false; response.error = "serial odom callback queue timed out"; return true;
    }
    if (echoed_odom_.header.stamp != stamp ||
        !same(echoed_odom_.pose.pose.position.x, request.x) ||
        !same(echoed_odom_.pose.pose.position.y, request.y) ||
        !same(echoed_odom_.twist.twist.linear.x, request.vx) ||
        !same(echoed_odom_.twist.twist.linear.y, request.vy) ||
        !same(echoed_odom_.twist.twist.angular.z, request.wz)) {
      response.ok = false; response.error = "accepted odom does not match executed state"; return true;
    }

    response.feedback = echoed_odom_;
    response.logical_time = request.simulation_time;
    const auto start = std::chrono::steady_clock::now();
    response.ok = planner_->computeVelocityCommands(response.command);
    response.compute_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    if (!response.ok) response.error = "plugin returned no valid velocity command";
    ++step_index_;
    return true;
  }

  void odomEcho(const nav_msgs::Odometry::ConstPtr& message) {
    echoed_odom_ = *message;
    ++odom_callbacks_;
  }

  ros::NodeHandle nh_, private_nh_, service_nh_;
  ros::CallbackQueue service_queue_;
  pluginlib::ClassLoader<nav_core::BaseLocalPlanner> loader_;
  tf2_ros::Buffer tf_;
  std::unique_ptr<costmap_2d::Costmap2DROS> costmap_;
  boost::shared_ptr<nav_core::BaseLocalPlanner> planner_;
  ros::Publisher clock_pub_, odom_pub_;
  ros::Subscriber odom_echo_sub_;
  ros::ServiceServer initialize_srv_, step_srv_;
  nav_msgs::Odometry echoed_odom_;
  std::string planner_plugin_, global_frame_, base_frame_, odom_topic_;
  double planner_period_ = 0.0;
  uint64_t odom_callbacks_ = 0;
  uint64_t step_index_ = 0;
  bool allow_reinitialize_ = false;
  bool initialized_ = false;
};

int main(int argc, char** argv) {
  ros::init(argc, argv, "scale_planner_bridge");
  try {
    PlannerBridge bridge;
    ros::AsyncSpinner service_spinner(1, bridge.serviceQueue());
    service_spinner.start();
    ros::waitForShutdown();
  } catch (const std::exception& error) {
    ROS_FATAL("Planner bridge initialization failed: %s", error.what());
    return 1;
  }
  return 0;
}

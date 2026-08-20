#include <costmap_2d/costmap_2d_ros.h>
#include <geometry_msgs/TransformStamped.h>
#include <nav_core/base_local_planner.h>
#include <nav_msgs/Odometry.h>
#include <pluginlib/class_loader.hpp>
#include <ros/callback_queue.h>
#include <tf2/LinearMath/Quaternion.h>
#include <tf2_ros/buffer.h>

#include <scale_planner_bridge/Initialize.h>
#include <scale_planner_bridge/Step.h>

#include <chrono>
#include <atomic>
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace {
geometry_msgs::Quaternion quaternion(double yaw) {
  tf2::Quaternion q;
  q.setRPY(0.0, 0.0, yaw);
  geometry_msgs::Quaternion result;
  result.x = q.x(); result.y = q.y(); result.z = q.z(); result.w = q.w();
  return result;
}
}  // namespace

class PlannerBridge {
 public:
  PlannerBridge()
      : nh_(), private_nh_("~"), loader_("nav_core", "nav_core::BaseLocalPlanner"),
        tf_(ros::Duration(10.0)), initialized_(false), odom_callbacks_(0) {
    private_nh_.param<std::string>("planner_plugin", planner_plugin_, "dwa_local_planner/DWAPlannerROS");
    private_nh_.param<std::string>("global_frame", global_frame_, "map");
    private_nh_.param<std::string>("base_frame", base_frame_, "base_link");
    private_nh_.param<std::string>("odom_topic", odom_topic_, "odom");
    // Costmap2DROS asks the buffer for transforms with a tolerance.  The bridge
    // supplies transforms synchronously, but tf2 still requires this flag to
    // permit those bounded lookups without a /tf listener thread.
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
    initialize_srv_ = nh_.advertiseService("initialize", &PlannerBridge::initialize, this);
    step_srv_ = nh_.advertiseService("step", &PlannerBridge::step, this);
  }

 private:
  bool initialize(scale_planner_bridge::Initialize::Request& request,
                  scale_planner_bridge::Initialize::Response& response) {
    if (initialized_) {
      response.ok = false; response.error = "bridge is already initialized"; return true;
    }
    if (request.map.info.resolution <= 0.0 || request.map.info.width == 0 || request.map.info.height == 0 ||
        request.map.data.size() != request.map.info.width * request.map.info.height || request.plan.poses.empty()) {
      response.ok = false; response.error = "map or plan is invalid"; return true;
    }
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
      // The observer proves that the just-published odometry traversed this
      // process's callback queue before a planning step proceeds.
      odom_echo_sub_ = nh_.subscribe(odom_topic_, 1, &PlannerBridge::odomEcho, this);
      const ros::WallTime connection_deadline = ros::WallTime::now() + ros::WallDuration(0.5);
      while (ros::ok() && odom_pub_.getNumSubscribers() < 1 && ros::WallTime::now() < connection_deadline) {
        ros::getGlobalCallbackQueue()->callAvailable(ros::WallDuration(0.005));
      }
      if (odom_pub_.getNumSubscribers() < 1) {
        response.ok = false; response.error = "odom loopback subscription did not connect"; return true;
      }
      if (!planner_->setPlan(request.plan.poses)) {
        response.ok = false; response.error = "plugin rejected fixed global plan"; return true;
      }
    } catch (const pluginlib::PluginlibException& error) {
      response.ok = false; response.error = error.what(); return true;
    }
    initialized_ = true;
    response.ok = true;
    return true;
  }

  bool step(scale_planner_bridge::Step::Request& request, scale_planner_bridge::Step::Response& response) {
    if (!initialized_) {
      response.ok = false; response.error = "initialize must be called first"; return true;
    }
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
    odom.pose.pose.position.x = request.x; odom.pose.pose.position.y = request.y; odom.pose.pose.orientation = quaternion(request.yaw);
    odom.twist.twist.linear.x = request.vx; odom.twist.twist.linear.y = request.vy; odom.twist.twist.angular.z = request.wz;
    const uint64_t previous_callbacks = odom_callbacks_.load();
    odom_pub_.publish(odom);
    const ros::WallTime deadline = ros::WallTime::now() + ros::WallDuration(0.2);
    while (ros::ok() && odom_callbacks_.load() == previous_callbacks && ros::WallTime::now() < deadline) {
      ros::WallDuration(0.001).sleep();
    }
    if (odom_callbacks_.load() == previous_callbacks) {
      response.ok = false; response.error = "odom loopback callback timed out"; return true;
    }
    const auto start = std::chrono::steady_clock::now();
    response.ok = planner_->computeVelocityCommands(response.command);
    response.compute_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
    response.goal_reached = planner_->isGoalReached();
    if (!response.ok) response.error = "plugin returned no valid velocity command";
    return true;
  }

  void odomEcho(const nav_msgs::Odometry::ConstPtr&) { ++odom_callbacks_; }

  ros::NodeHandle nh_, private_nh_;
  pluginlib::ClassLoader<nav_core::BaseLocalPlanner> loader_;
  tf2_ros::Buffer tf_;
  std::unique_ptr<costmap_2d::Costmap2DROS> costmap_;
  boost::shared_ptr<nav_core::BaseLocalPlanner> planner_;
  ros::Publisher odom_pub_;
  ros::Subscriber odom_echo_sub_;
  ros::ServiceServer initialize_srv_, step_srv_;
  std::string planner_plugin_, global_frame_, base_frame_, odom_topic_;
  bool initialized_;
  std::atomic<uint64_t> odom_callbacks_;
};

int main(int argc, char** argv) {
  ros::init(argc, argv, "scale_planner_bridge");
  PlannerBridge bridge;
  ros::AsyncSpinner spinner(2);
  spinner.start();
  ros::waitForShutdown();
  return 0;
}

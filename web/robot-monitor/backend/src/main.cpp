#include "crow.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdlib>
#include <mutex>
#include <string>
#include <thread>
#include <unordered_set>

namespace {
std::mutex clients_mutex;
std::unordered_set<crow::websocket::connection*> clients;
std::unordered_set<crow::websocket::connection*> authorized_clients;
std::atomic_bool keep_running{true};
std::atomic_int mission_mode{0};  // 0=idle, 1=patrolling, 2=paused, 3=emergency stop

const std::string& control_password() {
  static const std::string password = [] {
    const char* value = std::getenv("ROBOT_CONTROL_PASSWORD");
    return value ? std::string(value) : std::string();
  }();
  return password;
}

std::string mission_state() {
  switch (mission_mode.load()) {
    case 1: return "巡检中";
    case 2: return "已暂停";
    case 3: return "紧急停止";
    default: return "待命";
  }
}

bool is_authorized(crow::websocket::connection& connection) {
  std::lock_guard<std::mutex> lock(clients_mutex);
  return authorized_clients.find(&connection) != authorized_clients.end();
}

void broadcast(std::string message) {
  std::lock_guard<std::mutex> lock(clients_mutex);
  for (auto* client : clients) client->send_text(message);
}

void simulator_loop() {
  using namespace std::chrono_literals;
  double temperature = 25.6;
  double humidity = 58.0;
  double noise = 46.0;
  double x = 0.0;
  double battery = 87.0;

  while (keep_running.load()) {
    const auto now = std::chrono::system_clock::now().time_since_epoch();
    const auto timestamp = std::chrono::duration_cast<std::chrono::milliseconds>(now).count();
    const double t = timestamp / 1000.0;
    const bool moving = mission_mode.load() == 1;
    temperature = 25.6 + std::sin(t / 12.0) * 1.2;
    humidity = 58.0 + std::sin(t / 16.0) * 3.0;
    noise = 46.0 + std::sin(t / 4.0) * 4.0;
    if (moving) {
      x += 0.12;
      battery = std::max(0.0, battery - 0.002);
    }

    crow::json::wvalue message;
    message["type"] = "robot_status";
    message["timestamp"] = timestamp;
    message["source"] = "robot";
    message["sensors"]["temperature"] = std::round(temperature * 10.0) / 10.0;
    message["sensors"]["humidity"] = std::round(humidity * 10.0) / 10.0;
    message["sensors"]["noise"] = std::round(noise * 10.0) / 10.0;
    message["robot"]["online"] = true;
    message["robot"]["taskStatus"] = mission_state();
    message["robot"]["battery"] = std::round(battery * 10.0) / 10.0;
    message["robot"]["speed"] = moving ? 0.32 : 0.0;
    message["pose"]["x"] = std::round(x * 100.0) / 100.0;
    message["pose"]["y"] = std::round(std::sin(x / 2.0) * 120.0) / 100.0;
    message["pose"]["yaw"] = std::round(std::cos(x / 3.0) * 35.0) / 100.0;
    broadcast(message.dump());
    std::this_thread::sleep_for(1s);
  }
}

void send_auth_result(crow::websocket::connection& connection, bool ok, const std::string& message) {
  crow::json::wvalue result;
  result["type"] = "auth_result";
  result["ok"] = ok;
  result["message"] = message;
  connection.send_text(result.dump());
}

void handle_message(crow::websocket::connection& connection, const std::string& payload) {
  const auto request = crow::json::load(payload);
  if (!request || !request.has("type")) {
    crow::json::wvalue result;
    result["type"] = "command_result";
    result["ok"] = false;
    result["message"] = "消息格式错误";
    connection.send_text(result.dump());
    return;
  }

  const std::string type = request["type"].s();
  if (type == "auth") {
    if (control_password().empty()) {
      send_auth_result(connection, false, "后端尚未设置 ROBOT_CONTROL_PASSWORD");
      return;
    }
    const bool ok = request.has("password") && request["password"].s() == control_password();
    {
      std::lock_guard<std::mutex> lock(clients_mutex);
      if (ok) authorized_clients.insert(&connection);
      else authorized_clients.erase(&connection);
    }
    send_auth_result(connection, ok, ok ? "控制权限已解锁" : "控制密码错误");
    return;
  }

  if (type == "lock") {
    std::lock_guard<std::mutex> lock(clients_mutex);
    authorized_clients.erase(&connection);
    return;
  }

  crow::json::wvalue result;
  result["type"] = "command_result";
  result["ok"] = false;
  if (type != "command" || !request.has("command")) {
    result["message"] = "命令格式错误";
    connection.send_text(result.dump());
    return;
  }
  if (!is_authorized(connection)) {
    result["code"] = "unauthorized";
    result["message"] = "控制权限未解锁，命令已拒绝";
    connection.send_text(result.dump());
    return;
  }

  const std::string command = request["command"].s();
  if (command == "start_patrol") {
    mission_mode.store(1);
    result["ok"] = true;
    result["message"] = "模拟后端已接收：开始巡检（未驱动真实电机）";
  } else if (command == "pause_patrol") {
    mission_mode.store(2);
    result["ok"] = true;
    result["message"] = "模拟后端已接收：暂停巡检";
  } else if (command == "stop_patrol") {
    mission_mode.store(0);
    result["ok"] = true;
    result["message"] = "模拟后端已接收：结束巡检";
  } else if (command == "emergency_stop") {
    mission_mode.store(3);
    result["ok"] = true;
    result["message"] = "模拟后端已接收：紧急停止";
  } else {
    result["message"] = "不支持的命令";
  }
  result["mission_state"] = mission_state();
  connection.send_text(result.dump());
}
}  // namespace

int main() {
  crow::SimpleApp app;

  CROW_ROUTE(app, "/api/health")([] {
    crow::json::wvalue body;
    body["ok"] = true;
    body["service"] = "robot-mock-backend";
    body["safe_mode"] = true;
    body["control_auth_configured"] = !control_password().empty();
    return crow::response{body};
  });

  CROW_WEBSOCKET_ROUTE(app, "/ws")
    .onopen([](crow::websocket::connection& connection) {
      std::lock_guard<std::mutex> lock(clients_mutex);
      clients.insert(&connection);
    })
    .onclose([](crow::websocket::connection& connection, const std::string&) {
      std::lock_guard<std::mutex> lock(clients_mutex);
      clients.erase(&connection);
      authorized_clients.erase(&connection);
    })
    .onmessage([](crow::websocket::connection& connection, const std::string& data, bool is_binary) {
      if (!is_binary) handle_message(connection, data);
    });

  std::signal(SIGINT, [](int) { keep_running.store(false); });
  std::thread simulator(simulator_loop);
  app.port(8080).multithreaded().run();
  keep_running.store(false);
  simulator.join();
}

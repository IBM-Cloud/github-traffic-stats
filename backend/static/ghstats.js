// Callback functions to add or delete a repository from the database
// Written by Henrik Loeser, hloeser@de.ibm.com

// Add a repository and display returned message
function addRepo() {
  var xhttp;
  var orgname = document.forms['newrepo'].elements['orgname'].value;
  var reponame = document.forms['newrepo'].elements['reponame'].value;
  xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function () {
    if (xhttp.readyState == XMLHttpRequest.DONE) {
      var response = JSON.parse(xhttp.responseText);
      document.getElementById("messageResult").style.display = "block";
      document.getElementById("plogmessage").innerHTML = "Message: " + response.message;
      t=$('#repolist').DataTable();
      t.row.add([response.repoid, orgname, reponame ]).node().id=response.repoid;
      t.draw();
      document.getElementById("orgname").value = '';
      document.getElementById("reponame").value = '';
    }
  };
  xhttp.open('POST', "/api/newrepo");
  xhttp.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
  var postVars = 'orgname=' + orgname + '&reponame=' + reponame;
  xhttp.send(postVars);
  return false;
}

// Delete an existing repository by ID
function deleteRepo() {
  var xhttp;
  var repoid = document.forms['deleterepo'].elements['repoid'].value;
  xhttp = new XMLHttpRequest();
  xhttp.onreadystatechange = function () {
    if (xhttp.readyState == XMLHttpRequest.DONE) {
      var response = JSON.parse(xhttp.responseText);
      document.getElementById("messageResult").style.display = "block";
      document.getElementById("plogmessage").innerHTML = "Message: " + response.message;
      // delete from shown HTML table and redraw
      $('#repolist').DataTable().row("#"+repoid).remove().draw();
      document.getElementById("repoid").value = '';
    }
  };
  xhttp.open('POST', "/api/deleterepo");
  xhttp.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
  var postVars = 'repoid=' + repoid;
  xhttp.send(postVars);
  return false;
}

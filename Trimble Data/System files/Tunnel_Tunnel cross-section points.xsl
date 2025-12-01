<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet version="1.0"    
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:msxsl="urn:schemas-microsoft-com:xslt">

<!-- (c) 2016, Trimble Inc. All rights reserved.                                               -->
<!-- Permission is hereby granted to use, copy, modify, or distribute this style sheet for any -->
<!-- purpose and without fee, provided that the above copyright notice appears in all copies   -->
<!-- and that both the copyright notice and the limited warranty and restricted rights notice  -->
<!-- below appear in all supporting documentation.                                             -->

<!-- TRIMBLE INC. PROVIDES THIS STYLE SHEET "AS IS" AND WITH ALL FAULTS.                       -->
<!-- TRIMBLE INC. SPECIFICALLY DISCLAIMS ANY IMPLIED WARRANTY OF MERCHANTABILITY               -->
<!-- OR FITNESS FOR A PARTICULAR USE. TRIMBLE INC. DOES NOT WARRANT THAT THE                   -->
<!-- OPERATION OF THIS STYLE SHEET WILL BE UNINTERRUPTED OR ERROR FREE.                        -->

<xsl:output method="text" omit-xml-declaration="yes" encoding="ISO-8859-1"/>

<!-- Set the numeric display details i.e. decimal point, thousands separator etc -->
<xsl:variable name="DecPt" select="'.'"/>    <!-- Change as appropriate for US/European -->
<xsl:variable name="GroupSep" select="','"/> <!-- Change as appropriate for US/European -->
<!-- Also change decimal-separator & grouping-separator in decimal-format below 
     as appropriate for US/European output -->
<xsl:decimal-format name="Standard" 
                    decimal-separator="."
                    grouping-separator=","
                    infinity="Infinity"
                    minus-sign="-"
                    NaN="?"
                    percent="%"
                    per-mille="&#2030;"
                    zero-digit="0" 
                    digit="#" 
                    pattern-separator=";" />

<xsl:variable name="DecPl0" select="'#0'"/>
<xsl:variable name="DecPl1" select="concat('#0', $DecPt, '0')"/>
<xsl:variable name="DecPl2" select="concat('#0', $DecPt, '00')"/>
<xsl:variable name="DecPl3" select="concat('#0', $DecPt, '000')"/>
<xsl:variable name="DecPl4" select="concat('#0', $DecPt, '0000')"/>
<xsl:variable name="DecPl5" select="concat('#0', $DecPt, '00000')"/>
<xsl:variable name="DecPl8" select="concat('#0', $DecPt, '00000000')"/>

<xsl:variable name="Pi" select="3.14159265358979323846264"/>
<xsl:variable name="halfPi" select="$Pi div 2.0"/>

<xsl:variable name="DegreesSymbol" select="'.'"/>
<xsl:variable name="MinutesSymbol" select="''"/>
<xsl:variable name="SecondsSymbol" select="''"/>

<xsl:variable name="fileExt" select="'csv'"/>

<!-- User variable definitions - Appropriate fields are displayed on the       -->
<!-- Survey Controller screen to allow the user to enter specific values       -->
<!-- which can then be used within the style sheet definition to control the   -->
<!-- output data.                                                              -->
<!--                                                                           -->
<!-- All user variables must be identified by a variable element definition    -->
<!-- named starting with 'userField' (case sensitive) followed by one or more  -->
<!-- characters uniquely identifying the user variable definition.             -->
<!--                                                                           -->
<!-- The text within the 'select' field for the user variable description      -->
<!-- references the actual user variable and uses the '|' character to         -->
<!-- separate the definition details into separate fields as follows:          -->
<!-- For all user variables the first field must be the name of the user       -->
<!-- variable itself (this is case sensitive) and the second field is the      -->
<!-- prompt that will appear on the Survey Controller screen.                  -->
<!-- The third field defines the variable type - there are four possible       -->
<!-- variable types: Double, Integer, String and StringMenu.  These variable   -->
<!-- type references are not case sensitive.                                   -->
<!-- The fields that follow the variable type change according to the type of  -->
<!-- variable as follow:                                                       -->
<!-- Double and Integer: Fourth field = optional minimum value                 -->
<!--                     Fifth field = optional maximum value                  -->
<!--   These minimum and maximum values are used by the Survey Controller for  -->
<!--   entry validation.                                                       -->
<!-- String: No further fields are needed or used.                             -->
<!-- StringMenu: Fourth field = number of menu items                           -->
<!--             Remaining fields are the actual menu items - the number of    -->
<!--             items provided must equal the specified number of menu items. -->
<!--                                                                           -->
<!-- The style sheet must also define the variable itself, named according to  -->
<!-- the definition.  The value within the 'select' field will be displayed in -->
<!-- the Survey Controller as the default value for the item.                  -->

<!-- Define key to speed up searching -->
<xsl:key name="obsPointID-search" match="//JOBFile/FieldBook/PointRecord" use="@ID"/>

<!-- **************************************************************** -->
<!-- Set global variables from the Environment section of JobXML file -->
<!-- **************************************************************** -->
<xsl:variable name="DistUnit"   select="/JOBFile/Environment/DisplaySettings/DistanceUnits" />
<xsl:variable name="AngleUnit"  select="/JOBFile/Environment/DisplaySettings/AngleUnits" />
<xsl:variable name="CoordOrder" select="/JOBFile/Environment/DisplaySettings/CoordinateOrder" />
<xsl:variable name="TempUnit"   select="/JOBFile/Environment/DisplaySettings/TemperatureUnits" />
<xsl:variable name="PressUnit"  select="/JOBFile/Environment/DisplaySettings/PressureUnits" />

<!-- Setup conversion factor for coordinate and distance values -->
<!-- Dist/coord values in JobXML file are always in metres -->
<xsl:variable name="DistConvFactor">
  <xsl:choose>
    <xsl:when test="$DistUnit='Metres'">1.0</xsl:when>
    <xsl:when test="$DistUnit='InternationalFeet'">3.280839895</xsl:when>
    <xsl:when test="$DistUnit='USSurveyFeet'">3.2808333333357</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for angular values -->
<!-- Angular values in JobXML file are always in decimal degrees -->
<xsl:variable name="AngleConvFactor">
  <xsl:choose>
    <xsl:when test="$AngleUnit='DMSDegrees'">1.0</xsl:when>
    <xsl:when test="$AngleUnit='Gons'">1.111111111111</xsl:when>
    <xsl:when test="$AngleUnit='Mils'">17.77777777777</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup boolean variable for coordinate order -->
<xsl:variable name="NECoords">
  <xsl:choose>
    <xsl:when test="$CoordOrder='North-East-Elevation'">true</xsl:when>
    <xsl:when test="$CoordOrder='X-Y-Z'">true</xsl:when>
    <xsl:otherwise>false</xsl:otherwise>
  </xsl:choose>
</xsl:variable>

<!-- Setup conversion factor for pressure values -->
<!-- Pressure values in JobXML file are always in millibars (hPa) -->
<xsl:variable name="PressConvFactor">
  <xsl:choose>
    <xsl:when test="$PressUnit='MilliBar'">1.0</xsl:when>
    <xsl:when test="$PressUnit='InchHg'">0.029529921</xsl:when>
    <xsl:when test="$PressUnit='mmHg'">0.75006</xsl:when>
    <xsl:otherwise>1.0</xsl:otherwise>
  </xsl:choose>
</xsl:variable>


<!-- **************************************************************** -->
<!-- ************************** Main Loop *************************** -->
<!-- **************************************************************** -->
<xsl:template match="/" >

  <!-- Select the FieldBook node to process -->
  <xsl:apply-templates select="JOBFile/FieldBook" />

</xsl:template>


<!-- **************************************************************** -->
<!-- ***************** FieldBook Node Processing ******************** -->
<!-- **************************************************************** -->
<xsl:template match="FieldBook">

  <!-- The tunnel delta points will be output with the station value as their northing   -->
  <!-- value and the computed distance (as a set of chords summed together) left and     -->
  <!-- right of the centreline as their easting value.  The Delta value will be output   -->
  <!-- as the elevation value.                                                           -->

  <xsl:variable name="pointData">
    <xsl:for-each select="TunnelCrossSectionRecord">
      <xsl:variable name="nominalStn" select="Station"/>

      <xsl:variable name="profilePoints">
        <xsl:for-each select="TunnelPointDeltaRecord">
          <xsl:variable name="obsID" select="ObservationID"/>
          <!-- Add point to node set variable if it is the first occurence of this point (to maintain the order) -->
          <xsl:if test="count(preceding-sibling::TunnelPointDeltaRecord[(ObservationID = $obsID) and (string(number(Delta)) != 'NaN')]) = 0">
            <!-- Now we want to make sure that we use the last set of values available for a point -->
            <xsl:choose>
              <xsl:when test="count(following-sibling::TunnelPointDeltaRecord[(ObservationID = $obsID) and (string(number(Delta)) != 'NaN')]) &gt; 0">
                <!-- Get the details for the last deltas record for this point -->
                <xsl:for-each select="following-sibling::TunnelPointDeltaRecord[(ObservationID = $obsID) and (string(number(Delta)) != 'NaN')][last()]">
                  <xsl:copy>
                    <xsl:copy-of select="*"/>
                    <!-- Add the point name as an element as well -->
                    <xsl:element name="Name">
                      <xsl:for-each select="key('obsPointID-search', ObservationID)">
                        <xsl:value-of select="Name"/>
                      </xsl:for-each>
                    </xsl:element>
                  </xsl:copy>
                </xsl:for-each>
              </xsl:when>
              <xsl:otherwise>  <!-- This is the one and only delta record for this point -->
                <xsl:if test="string(number(Delta)) != 'NaN'">  <!-- Valid measurement -->
                  <xsl:copy>
                    <xsl:copy-of select="*"/>
                    <!-- Add the point name as an element as well -->
                    <xsl:element name="Name">
                      <xsl:for-each select="key('obsPointID-search', ObservationID)">
                        <xsl:value-of select="Name"/>
                      </xsl:for-each>
                    </xsl:element>
                  </xsl:copy>
                </xsl:if>
              </xsl:otherwise>
            </xsl:choose>
          </xsl:if>
        </xsl:for-each>
      </xsl:variable>

      <xsl:variable name="reversedProfilePoints">
        <xsl:call-template name="reversedNodeSet">
          <xsl:with-param name="originalNodeSet" select="$profilePoints"/>
          <xsl:with-param name="count" select="count(msxsl:node-set($profilePoints)/*)"/>
          <xsl:with-param name="item" select="count(msxsl:node-set($profilePoints)/*)"/>
        </xsl:call-template>
      </xsl:variable>

      <!-- Get the left side points -->
      <xsl:for-each select="msxsl:node-set($profilePoints)/TunnelPointDeltaRecord[HorizontalOffset &lt;= 0]">
        <xsl:element name="point">
          <xsl:element name="name">
            <xsl:value-of select="Name"/>
          </xsl:element>

          <xsl:element name="coords">
            <xsl:element name="north">
              <xsl:value-of select="$nominalStn + DeltaStation"/>
            </xsl:element>

            <!-- Compute the sum of the chords between the points leading up to this point -->
            <xsl:variable name="offsetDist">
              <xsl:element name="component">  <!-- Compute the first chord (from 0,0) every time -->
                <xsl:for-each select="msxsl:node-set($profilePoints)/TunnelPointDeltaRecord[1]">
                  <xsl:call-template name="Sqrt">
                    <xsl:with-param name="num" select="HorizontalOffset * HorizontalOffset + VerticalOffset * VerticalOffset"/>
                  </xsl:call-template>
                </xsl:for-each>
              </xsl:element>

              <xsl:variable name="count" select="position()"/>
              <xsl:for-each select="preceding-sibling::*[position() &lt; $count]">
                <xsl:variable name="nextHzOffset" select="following-sibling::*[1]/HorizontalOffset"/>
                <xsl:variable name="nextVtOffset" select="following-sibling::*[1]/VerticalOffset"/>
                <xsl:element name="component">
                  <xsl:call-template name="Sqrt">
                    <xsl:with-param name="num" select="(HorizontalOffset - $nextHzOffset) * (HorizontalOffset - $nextHzOffset) + (VerticalOffset - $nextVtOffset) * (VerticalOffset - $nextVtOffset)"/>
                  </xsl:call-template>
                </xsl:element>
              </xsl:for-each>
            </xsl:variable>

            <xsl:element name="east">
              <xsl:value-of select="sum(msxsl:node-set($offsetDist)/component) * -1"/> <!-- Negate the values to put them on the left side -->
            </xsl:element>

            <xsl:element name="elevation">
              <xsl:value-of select="Delta"/>
            </xsl:element>
          </xsl:element>
        </xsl:element>   <!-- point element -->
      </xsl:for-each>

      <!-- Get the right side points -->
      <xsl:for-each select="msxsl:node-set($reversedProfilePoints)/TunnelPointDeltaRecord[HorizontalOffset &gt;= 0]">
        <xsl:element name="point">
          <xsl:element name="name">
            <xsl:value-of select="Name"/>
          </xsl:element>

          <xsl:element name="coords">
            <xsl:element name="north">
              <xsl:value-of select="$nominalStn + DeltaStation"/>
            </xsl:element>
            <!-- Compute the sum of the chords between the points leading up to this point -->
            <xsl:variable name="offsetDist">
              <xsl:element name="component">  <!-- Compute the first chord (from 0,0) every time -->
                <xsl:for-each select="msxsl:node-set($profilePoints)/TunnelPointDeltaRecord[1]">
                  <xsl:call-template name="Sqrt">
                    <xsl:with-param name="num" select="HorizontalOffset * HorizontalOffset + VerticalOffset * VerticalOffset"/>
                  </xsl:call-template>
                </xsl:for-each>
              </xsl:element>

              <xsl:variable name="count" select="position()"/>
              <xsl:for-each select="preceding-sibling::*[position() &lt; $count]">
                <xsl:variable name="nextHzOffset" select="following-sibling::*[1]/HorizontalOffset"/>
                <xsl:variable name="nextVtOffset" select="following-sibling::*[1]/VerticalOffset"/>
                <xsl:element name="component">
                  <xsl:call-template name="Sqrt">
                    <xsl:with-param name="num" select="(HorizontalOffset - $nextHzOffset) * (HorizontalOffset - $nextHzOffset) + (VerticalOffset - $nextVtOffset) * (VerticalOffset - $nextVtOffset)"/>
                  </xsl:call-template>
                </xsl:element>
              </xsl:for-each>
            </xsl:variable>

            <xsl:element name="east">
              <xsl:value-of select="sum(msxsl:node-set($offsetDist)/component)"/>
            </xsl:element>

            <xsl:element name="elevation">
              <xsl:value-of select="Delta"/>
            </xsl:element>
          </xsl:element>
        </xsl:element>   <!-- point element -->
      </xsl:for-each>

    </xsl:for-each>
  </xsl:variable>

  <!-- Write the data out as a csv file -->
  <xsl:for-each select="msxsl:node-set($pointData)/point">
    <xsl:value-of select="name"/>
    <xsl:text>,</xsl:text>
    
    <xsl:value-of select="format-number(coords/east * $DistConvFactor, $DecPl3, 'Standard')"/>
    <xsl:text>,</xsl:text>

    <xsl:value-of select="format-number(coords/north * $DistConvFactor, $DecPl3, 'Standard')"/>
    <xsl:text>,</xsl:text>

    <xsl:value-of select="format-number(coords/elevation * $DistConvFactor, $DecPl3, 'Standard')"/>
    <xsl:call-template name="NewLine"/>
  </xsl:for-each>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********** Return  a Reverse Order Node Set Variable *********** -->
<!-- **************************************************************** -->
<xsl:template name="reversedNodeSet">
  <xsl:param name="originalNodeSet"/>
  <xsl:param name="count"/>
  <xsl:param name="item"/>

  <!-- This recursive function will return the passed in node set in the reverse order -->
  <xsl:if test="$item &gt; 0">
    <xsl:choose>
      <xsl:when test="$item = $count">
        <xsl:for-each select="msxsl:node-set($originalNodeSet)/*[last()]">  <!-- Get the last element (returned first) -->
          <xsl:copy>
            <xsl:copy-of select="*"/>
          </xsl:copy>
        </xsl:for-each>
      </xsl:when>

      <xsl:otherwise>  <!-- Copy the appropriate preceding element -->
        <xsl:for-each select="msxsl:node-set($originalNodeSet)/*[last()]">  <!-- Get the last element -->
          <xsl:for-each select="preceding-sibling::*[$count - $item]">      <!-- get the required preceding element -->
            <xsl:copy>
              <xsl:copy-of select="*"/>
            </xsl:copy>
          </xsl:for-each>
        </xsl:for-each>
      </xsl:otherwise>
    </xsl:choose>

    <!-- Recurse the function decrementing the item value -->
    <xsl:call-template name="reversedNodeSet">
      <xsl:with-param name="originalNodeSet" select="$originalNodeSet"/>
      <xsl:with-param name="count" select="$count"/>
      <xsl:with-param name="item" select="$item - 1"/>
    </xsl:call-template>
  </xsl:if>

</xsl:template>


<!-- **************************************************************** -->
<!-- ********************** New Line Output ************************* -->
<!-- **************************************************************** -->
<xsl:template name="NewLine">
<xsl:text>&#10;</xsl:text>
</xsl:template>


<!-- **************************************************************** -->
<!-- *************** Return the square root of a value ************** -->
<!-- **************************************************************** -->
<xsl:template name="Sqrt">
  <xsl:param name="num" select="0"/>       <!-- The number you want to find the square root of -->
  <xsl:param name="try" select="1"/>       <!-- The current 'try'.  This is used internally. -->
  <xsl:param name="iter" select="1"/>      <!-- The current iteration, checked against maxiter to limit loop count - used internally -->
  <xsl:param name="maxiter" select="20"/>  <!-- Set this up to insure against infinite loops - used internally -->

  <!-- This template uses Sir Isaac Newton's method of finding roots -->

  <xsl:choose>
    <xsl:when test="$try * $try = $num or $iter &gt; $maxiter">
      <xsl:value-of select="$try"/>
    </xsl:when>
    <xsl:otherwise>
      <xsl:call-template name="Sqrt">
        <xsl:with-param name="num" select="$num"/>
        <xsl:with-param name="try" select="$try - (($try * $try - $num) div (2 * $try))"/>
        <xsl:with-param name="iter" select="$iter + 1"/>
        <xsl:with-param name="maxiter" select="$maxiter"/>
      </xsl:call-template>
    </xsl:otherwise>
  </xsl:choose>
</xsl:template>


</xsl:stylesheet>